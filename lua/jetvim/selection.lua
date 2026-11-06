local M = { states = {}, cache = {} }
local function same(a, b) return a and b and vim.deep_equal(a, b) end
local function context()
  local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
  local starts, offset = {}, 0
  for i, line in ipairs(lines) do starts[i], offset = offset, offset + #line + 1 end
  local text = table.concat(lines, '\n')
  local function absolute(row, col) return math.min(#text, (starts[row + 1] or #text) + col) end
  local function position(value)
    for i = #lines, 1, -1 do if value >= starts[i] then return i - 1, value - starts[i] end end
    return 0, 0
  end
  return lines, starts, text, absolute, position
end
local function structural_ranges(lines, starts, text, filetype)
  local ranges, stack, tokens, paren_ends = {}, {}, {}, {}
  local function add(a, b, trim)
    if trim then
      local value = text:sub(a + 1, b)
      local left = #(value:match('^%s*') or '')
      local right = #(value:match('%s*$') or '')
      a, b = a + left, b - right
    end
    if b > a then ranges[#ranges + 1] = { a, b } end
  end
  local slash_comments = ({ c = true, cpp = true, go = true, rust = true, java = true,
    javascript = true, javascriptreact = true, typescript = true, typescriptreact = true,
    css = true, scss = true, jsonc = true, swift = true, kotlin = true, cs = true })[filetype]
  local hash_comments = ({ python = true, sh = true, bash = true, ruby = true, yaml = true, toml = true })[filetype]
  local regex_literals = filetype == 'javascript' or filetype == 'javascriptreact'
    or filetype == 'typescript' or filetype == 'typescriptreact'
  local line, i = 1, 1
  local last_significant = ''
  local function advance(target)
    local _, count = text:sub(i, target - 1):gsub('\n', '')
    line, i = line + count, target
  end
  local function long_string(prefix_length)
    local opening = i + prefix_length
    if text:byte(opening) ~= 91 then return false end
    local j = opening + 1
    while text:byte(j) == 61 do j = j + 1 end
    if text:byte(j) ~= 91 then return false end
    local close = ']' .. string.rep('=', j - opening - 1) .. ']'
    local finish = text:find(close, j + 1, true)
    if not finish then advance(#text + 1); return true end
    if prefix_length == 0 then add(i - 1, finish + #close - 1); add(j, finish - 1) end
    advance(finish + #close)
    return true
  end
  while i <= #text do
    local char, pair = text:sub(i, i), text:sub(i, i + 1)
    if filetype == 'lua' and pair == '--' then
      if not long_string(2) then advance(text:find('\n', i, true) or (#text + 1)) end
    elseif filetype == 'lua' and char == '[' and long_string(0) then
      -- Long Lua strings may contain bracket-like code.
    elseif slash_comments and pair == '//' or hash_comments and char == '#' then
      advance(text:find('\n', i, true) or (#text + 1))
    elseif slash_comments and pair == '/*' then
      local finish = text:find('*/', i + 2, true)
      advance(finish and finish + 2 or #text + 1)
    elseif regex_literals and char == '/' and (last_significant == ''
      or last_significant:match('^[=(:,%[!&|?{};]$')
      or last_significant == 'return' or last_significant == 'throw' or last_significant == 'case') then
      local j, in_class = i + 1, false
      while j <= #text and text:sub(j, j) ~= '\n' do
        local current = text:sub(j, j)
        if current == '\\' then j = j + 2
        elseif current == '[' then in_class = true; j = j + 1
        elseif current == ']' then in_class = false; j = j + 1
        elseif current == '/' and not in_class then break
        else j = j + 1 end
      end
      if text:sub(j, j) == '/' then
        local finish = j + 1
        while text:sub(finish, finish):match('%a') do finish = finish + 1 end
        add(i - 1, finish - 1); add(i, j - 1)
        advance(finish)
        last_significant = '/'
      else i = i + 1; last_significant = '/' end
    elseif char == '"' or char == "'" or char == '`' then
      local quote = text:sub(i, i + 2) == string.rep(char, 3) and string.rep(char, 3) or char
      local j = i + #quote
      while j <= #text do
        if text:sub(j, j) == '\\' and not (filetype == 'go' and quote == '`') then j = j + 2
        elseif text:sub(j, j + #quote - 1) == quote then break
        else j = j + 1 end
      end
      if j <= #text then add(i - 1, j + #quote - 1); add(i + #quote - 1, j - 1) end
      advance(math.min(#text + 1, j + #quote))
      last_significant = quote
    elseif char == '(' or char == '[' or char == '{' then
      stack[#stack + 1] = { char = char, offset = i - 1, line = line }
      last_significant = char
      i = i + 1
    elseif char == ')' or char == ']' or char == '}' then
      local expected = ({ [')'] = '(', [']'] = '[', ['}'] = '{' })[char]
      local opening = stack[#stack]
      if opening and opening.char == expected then
        table.remove(stack)
        add(opening.offset, i)
        add(opening.offset + 1, i - 1, true)
        if char == ')' then paren_ends[opening.offset] = i end
        if char == '}' then
          local first = lines[opening.line]:find('%S') or 1
          local same_line_parent = false
          for _, parent in ipairs(stack) do
            if parent.line == opening.line then same_line_parent = true; break end
          end
          -- A nested object on one line must not select the unrelated prefix
          -- before its enclosing object. Declaration headers only make sense
          -- outside same-line containers; JSON objects need no such header.
          if not same_line_parent and filetype ~= 'json' and filetype ~= 'jsonc' then
            add(starts[opening.line] + first - 1, i)
          end
        end
      end
      last_significant = char
      i = i + 1
    elseif char:match('[%a_]') then
      local first, last = text:find('[%a_][%w_]*', i)
      local word = text:sub(first, last)
      if filetype == 'lua' then
        tokens[#tokens + 1] = { word = word, first = i - 1, last = i + #word - 1, line = line }
      end
      i = i + #word
      last_significant = word
    else
      if char == '\n' then line = line + 1 end
      if not char:match('%s') then last_significant = char end
      i = i + 1
    end
  end
  if filetype == 'lua' then
    local blocks = {}
    for _, token in ipairs(tokens) do
      local word, top = token.word, blocks[#blocks]
      if word == 'if' or word == 'function' or word == 'for' or word == 'while' or word == 'repeat' then
        local body = token.last
        if word == 'function' then
          local parameters = text:find('(', token.last + 1, true)
          if parameters then body = paren_ends[parameters - 1] or body end
        end
        blocks[#blocks + 1] = { token = token, body = body, waiting = word == 'for' or word == 'while', waiting_then = word == 'if' }
      elseif word == 'do' then
        if top and top.waiting then top.waiting, top.body = false, token.last
        else blocks[#blocks + 1] = { token = token, body = token.last } end
      elseif word == 'then' and top and top.waiting_then then top.body, top.waiting_then = token.last, false
      elseif (word == 'end' or word == 'until') and top then
        table.remove(blocks)
        local finish = word == 'until' and starts[token.line] + #lines[token.line] or token.last
        add(top.token.first, finish)
        add(top.body, token.first, true)
        local first = lines[top.token.line]:find('%S') or 1
        add(starts[top.token.line] + first - 1, finish)
      end
    end
  end
  if filetype == 'python' or filetype == 'yaml' then
    local blocks, previous = {}, 0
    local function finish(block)
      if block.body and previous >= block.body then
        local row, last = block.row, previous
        add(starts[row] + (lines[row]:find('%S') or 1) - 1, starts[last] + #lines[last])
        add(starts[block.body] + (lines[block.body]:find('%S') or 1) - 1, starts[last] + #lines[last])
      end
    end
    for row, value in ipairs(lines) do
      if value:match('%S') and not value:match('^%s*#') then
        local indent = vim.fn.indent(row)
        local clause = value:match('^%s*(%a+)')
        local continuation = clause == 'else' or clause == 'elif' or clause == 'except' or clause == 'finally'
        while #blocks > 0 do
          local top = blocks[#blocks]
          if indent > top.indent or indent == top.indent and continuation then break end
          finish(table.remove(blocks))
        end
        local top = blocks[#blocks]
        if top and indent > top.indent then top.body = top.body or row end
        if value:gsub('%s+#.*$', ''):match(':%s*$') and not (continuation and top and indent == top.indent) then
          blocks[#blocks + 1] = { row = row, indent = indent }
        end
        previous = row
      end
    end
    while #blocks > 0 do finish(table.remove(blocks)) end
  end
  return ranges
end
function M.target(previous)
  local lines, starts, text, absolute, position = context()
  local cursor = vim.api.nvim_win_get_cursor(0)
  local row, col = cursor[1] - 1, cursor[2]
  local a = previous and absolute(previous[1], previous[2]) or absolute(row, col)
  local b = previous and absolute(previous[3], previous[4]) or a
  local candidates = {}
  local function add(first, last)
    if first <= a and last >= b and last > first and (first < a or last > b) then
      candidates[#candidates + 1] = { first, last }
    end
  end
  -- Use parser syntax nodes when available. Missing parsers never trigger downloads.
  local ok, parser = pcall(vim.treesitter.get_parser, 0, nil, { error = false })
  if ok and parser then
    pcall(function()
      parser:parse()
      parser:for_each_tree(function(tree)
        local start_row, start_col = position(a)
        local node = tree:root():named_descendant_for_range(start_row, start_col, start_row, start_col)
        while node do
          local sr, sc, er, ec = node:range()
          if node:type() ~= 'ERROR' then add(absolute(sr, sc), absolute(er, ec)) end
          node = node:parent()
        end
      end)
    end)
  end
  if not previous then
    local offset = 0
    while offset < #lines[row + 1] do
      local match = vim.fn.matchstrpos(lines[row + 1], [[\k\+]], offset)
      if match[2] < 0 then break end
      if match[2] <= col and match[3] >= col then add(starts[row + 1] + match[2], starts[row + 1] + match[3]); break end
      offset = match[3]
    end
  end
  local buf, tick = vim.api.nvim_get_current_buf(), vim.api.nvim_buf_get_changedtick(0)
  local cached = M.cache[buf]
  if not cached or cached.tick ~= tick or cached.filetype ~= vim.bo.filetype then
    cached = { tick = tick, filetype = vim.bo.filetype, ranges = structural_ranges(lines, starts, text, vim.bo.filetype) }
    M.cache[buf] = cached
  end
  for _, range in ipairs(cached.ranges) do add(range[1], range[2]) end
  local first_row, last_row = previous and previous[1] or row, previous and previous[3] or row
  if previous and previous[4] == 0 and last_row > first_row then last_row = last_row - 1 end
  local first = lines[first_row + 1]:find('%S') or 1
  add(starts[first_row + 1] + first - 1, starts[last_row + 1] + #lines[last_row + 1])
  add(0, #text)
  table.sort(candidates, function(x, y)
    if x[2] - x[1] == y[2] - y[1] then return x[1] > y[1] end
    return x[2] - x[1] < y[2] - y[1]
  end)
  if #candidates == 0 then return end
  local sr, sc = position(candidates[1][1])
  local er, ec = position(candidates[1][2])
  return { sr, sc, er, ec }
end
local function unchanged(buf, state)
  if not state or state.filetype ~= vim.bo[buf].filetype then return false end
  local tick = vim.api.nvim_buf_get_changedtick(buf)
  if state.tick ~= tick then
    -- Native writes (including autosave) increment changedtick without editing
    -- text. Preserve history only after comparing the exact saved line snapshot.
    if not vim.deep_equal(state.lines, vim.api.nvim_buf_get_lines(buf, 0, -1, false)) then return false end
    state.tick = tick
  end
  return true
end
function M.extend()
  local edit = require('jetvim.edit')
  local buf, tick = vim.api.nvim_get_current_buf(), vim.api.nvim_buf_get_changedtick(0)
  local previous, state = edit.selection(), M.states[buf]
  if not unchanged(buf, state) or not same(state.current, previous) then
    state = { tick = tick, filetype = vim.bo.filetype, history = {},
      lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false) }; M.states[buf] = state
  end
  local target = M.target(previous)
  if not target then return end
  state.history[#state.history + 1] = { range = previous, cursor = vim.api.nvim_win_get_cursor(0) }
  edit.set_selection(target)
  state.current = edit.selection()
end
function M.shrink()
  local edit = require('jetvim.edit')
  local state = M.states[vim.api.nvim_get_current_buf()]
  if not unchanged(vim.api.nvim_get_current_buf(), state)
    or not same(state.current, edit.selection()) then return end
  local previous = table.remove(state.history)
  if not previous then return end
  if previous.range then edit.set_selection(previous.range)
  else
    vim.cmd.normal({ args = { vim.keycode('<Esc>') }, bang = true })
    vim.api.nvim_win_set_cursor(0, previous.cursor)
  end
  state.current = edit.selection()
end
vim.api.nvim_create_autocmd('BufWipeout', { callback = function(event) M.cache[event.buf], M.states[event.buf] = nil, nil end })
return M
