-- Scoped, asynchronous Find in Files. User text is always an argv value.
local M = {}
local ns = vim.api.nvim_create_namespace('JetvimProjectSearch')
local limit = 500
function M.contains(scope, path)
  return scope == '/' or path == scope or path:sub(1, #scope + 1) == scope .. '/'
end
local function valid(win) return win and vim.api.nvim_win_is_valid(win) end
local function alive(state) return M.state == state and not state.closed end
local function display(text)
  return tostring(text):gsub('[%z\1-\31\127]', function(char)
    return ({ ['\n'] = '↵', ['\r'] = '␍', ['\t'] = '⇥' })[char] or '�'
  end)
end
local function query(state)
  return vim.api.nvim_buf_get_lines(state.input, 0, 1, false)[1] or ''
end
local function cancel(state)
  state.generation = state.generation + 1
  if state.timer then state.timer:stop(); state.timer:close(); state.timer = nil end
  if state.job then pcall(state.job.kill, state.job, 15); state.job = nil end
  state.busy = false
end
local function draw(state)
  if not alive(state) or not vim.api.nvim_buf_is_valid(state.results) or not valid(state.promptwin) or not valid(state.listwin) then return end
  state.draw_pending = false
  local height = vim.api.nvim_win_get_height(state.listwin)
  state.selected = math.max(1, math.min(state.selected, #state.items))
  local first, lines = math.max(1, state.selected - height + 1), {}
  local from, to = math.min(state.anchor or state.selected, state.selected), math.max(state.anchor or state.selected, state.selected)
  for i = first, math.min(#state.items, first + height - 1) do
    local item = state.items[i]
    lines[#lines + 1] = (i == state.selected and ' › ' or '   ') .. item.label
  end
  if #lines == 0 then lines = { '   ' .. (state.message or 'Type to search') } end
  vim.api.nvim_buf_set_lines(state.results, 0, -1, false, lines)
  vim.api.nvim_buf_clear_namespace(state.results, ns, 0, -1)
  if #state.items > 0 then
    for i = math.max(first, from), math.min(to, first + #lines - 1) do
      vim.api.nvim_buf_set_extmark(state.results, ns, i - first, 0, { line_hl_group = 'JetvimPickerSelected' })
    end
  end
  local status = state.busy and 'Searching…' or state.message or (#state.items .. (state.capped and '+' or '') .. ' results')
  if state.anchor and #state.items > 0 then status = status .. ' · ' .. (to - from + 1) .. ' selected' end
  vim.api.nvim_win_set_config(state.listwin, { footer = ' ' .. display(status) .. ' · ↑↓ choose · Enter open · Esc close ', footer_pos = 'left' })
end
local function schedule_draw(state)
  if state.draw_pending then return end
  state.draw_pending = true
  vim.schedule(function() if alive(state) then draw(state) end end)
end
local function selected_scope()
  local project, tree = require('jetvim.project'), require('jetvim.tree')
  local candidate = project.root
  if tree.is_tree_window(vim.api.nvim_get_current_win()) then
    local entry = tree.rows[vim.api.nvim_win_get_cursor(0)[1]]
    if entry then
      local stat = vim.uv.fs_stat(entry.path)
      candidate = (entry.directory or stat and stat.type == 'directory') and entry.path or vim.fs.dirname(entry.path)
    end
  end
  local scope = project.resolve(candidate)
  if not scope then return nil, 'Outside project (search blocked)' end
  local stat = vim.uv.fs_stat(scope)
  if not stat or stat.type ~= 'directory' then return nil, 'Selected directory is unavailable' end
  local label = scope == project.root and ((scope == '/' and '' or vim.fs.basename(scope)) .. '/ (project)') or scope:sub(#project.root + 2) .. '/'
  return scope, display(label)
end
local function run(state, text, generation)
  if not alive(state) or generation ~= state.generation then return end
  if not state.scope then state.message = 'Selected path is outside the project'; draw(state); return end
  -- Resolve again immediately before launching, in case a directory became a symlink.
  if require('jetvim.project').resolve(state.scope) ~= state.scope then
    state.message = 'Selected path is outside the project'; draw(state); return
  end
  if vim.fn.executable('rg') ~= 1 then state.message = 'Find in Files requires ripgrep (rg)'; draw(state); return end
  state.busy, state.message = true, nil
  draw(state)
  local remainder, stderr = '', ''
  local function current() return alive(state) and generation == state.generation end
  local function consume(line)
    if #state.items >= limit then state.capped = true; return end
    local ok, entry = pcall(vim.json.decode, line)
    if not ok or entry.type ~= 'match' then return end
    local data = entry.data
    if not data.path.text or not data.lines.text or not data.submatches or not data.submatches[1] then return end
    local path = require('jetvim.project').resolve(state.scope .. '/' .. data.path.text)
    if not path or not M.contains(state.scope, path) then return end
    local row, col = data.line_number, data.submatches[1].start
    state.items[#state.items + 1] = { path = path, line = row, col = col,
      label = display(data.path.text:gsub('^%./', '')) .. ':' .. row .. '  ' .. display(vim.trim(data.lines.text)) }
    if #state.items >= limit then state.capped = true end
  end
  local options = { cwd = state.scope, text = true, timeout = 10000,
    stdout = function(err, data)
      if not current() or not data or state.capped then return end
      -- Decode on the main loop: path validation uses Neovim's filesystem helpers.
      vim.schedule(function()
        if not current() or state.capped then return end
        if err then state.message = 'Search output failed'; return end
        remainder = remainder .. data
        if #remainder > 3 * 1024 * 1024 then state.capped = true; state.message = 'Search output limit reached'
        else
          while true do
            local ending = remainder:find('\n', 1, true)
            if not ending then break end
            local line = remainder:sub(1, ending - 1); remainder = remainder:sub(ending + 1)
            consume(line)
            if state.capped then break end
          end
        end
        if state.capped and state.job then pcall(state.job.kill, state.job, 15) end
        schedule_draw(state)
      end)
    end,
    stderr = function(_, data) if data then stderr = (stderr .. data):sub(1, 500) end end,
  }
  local ok, job = pcall(vim.system, { 'rg', '--json', '--fixed-strings', '--hidden', '--max-count', '100',
    '--max-filesize', '2M', '-g', '!.git', '-g', '!.jetvim', '-g', '!.idea', '-g', '!node_modules', '--', text, '.' }, options,
    function(result)
      vim.schedule(function()
        if not current() then return end
        if remainder ~= '' and not state.capped then consume(remainder) end
        state.busy, state.job = false, nil
        if state.capped then state.message = state.message or (#state.items .. '+ results (limit)')
        elseif result.code ~= 0 and result.code ~= 1 then
          state.message = result.code == 124 and 'Search timed out' or ('Search failed: ' .. display(stderr ~= '' and stderr or tostring(result.code)))
        else state.message = #state.items == 0 and 'No matches' or (#state.items .. ' results') end
        draw(state)
      end)
    end)
  if not ok then state.busy = false; state.message = 'Cannot start ripgrep'; draw(state)
  elseif current() and state.busy then state.job = job end
end
function M.change(immediate)
  local state = M.state
  if not state or not alive(state) then return end
  local text = query(state)
  if text == state.query and not immediate then return end
  cancel(state)
  state.query, state.items, state.selected, state.capped, state.anchor = text, {}, 1, false, nil
  state.message = text == '' and 'Type to search' or 'Waiting…'
  draw(state)
  if text == '' then return end
  local generation = state.generation
  if immediate then run(state, text, generation); return end
  state.timer = vim.uv.new_timer()
  state.timer:start(200, 0, vim.schedule_wrap(function()
    if not alive(state) or generation ~= state.generation then return end
    state.timer:stop(); state.timer:close(); state.timer = nil
    run(state, text, generation)
  end))
end
function M.close(after)
  local state = M.state
  if not state or state.closing then return end
  if vim.fn.mode() == 'i' and vim.api.nvim_get_current_win() == state.promptwin then
    vim.cmd.stopinsert()
    vim.schedule(function() if alive(state) then M.close(after) end end)
    return
  end
  state.closing, state.closed = true, true
  cancel(state); M.state = nil
  for _, win in ipairs({ state.promptwin, state.listwin }) do if valid(win) then pcall(vim.api.nvim_win_close, win, true) end end
  for _, buf in ipairs({ state.input, state.results }) do if vim.api.nvim_buf_is_valid(buf) then pcall(vim.api.nvim_buf_delete, buf, { force = true }) end end
  if valid(state.origin) then vim.api.nvim_set_current_win(state.origin) end
  if after then after()
  elseif state.typing and valid(state.origin) and vim.api.nvim_get_current_win() == state.origin and vim.bo.buftype == '' then vim.cmd.startinsert() end
end
function M.choose()
  local state = M.state
  if not state then return end
  if query(state) ~= state.query then M.change(true); return end
  if state.timer or state.busy then return end
  local item = state.items[state.selected]
  if item then M.close(function() require('jetvim.project').open(item.path, item.line, item.col) end) end
end
local function move(state, direction, extend, page, boundary)
  if not alive(state) then return end
  if query(state) ~= state.query then M.change(); return end
  if #state.items == 0 then return end
  local current = state.selected
  if extend then
    state.anchor = state.anchor or current
  elseif state.anchor then
    -- Plain arrows collapse a range before moving again, as editor selections do.
    current = direction < 0 and math.min(state.anchor, current) or math.max(state.anchor, current)
    state.anchor = nil
    if not page and not boundary then state.selected = current; draw(state); return end
  end
  local step = page and vim.api.nvim_win_get_height(state.listwin) or 1
  state.selected = boundary and (direction < 0 and 1 or #state.items)
    or math.max(1, math.min(#state.items, current + direction * step))
  draw(state)
end
function M.geometry()
  local state = M.state
  if not state or not valid(state.promptwin) or not valid(state.listwin) then return end
  local width = math.max(1, math.min(100, vim.o.columns - 6))
  local height = math.max(1, math.min(12, vim.o.lines - 10))
  local row, col = math.max(0, math.floor((vim.o.lines - height - 5) / 2)), math.max(0, math.floor((vim.o.columns - width) / 2))
  vim.api.nvim_win_set_config(state.promptwin, { relative = 'editor', row = row, col = col, width = width, height = 1 })
  vim.api.nvim_win_set_config(state.listwin, { relative = 'editor', row = row + 3, col = col, width = width, height = height })
end
function M.open()
  if M.state and valid(M.state.promptwin) and vim.api.nvim_get_current_win() == M.state.promptwin then vim.cmd.startinsert(); return end
  local scope, label = selected_scope()
  local origin, typing = vim.api.nvim_get_current_win(), vim.bo.buftype == ''
  if M.state then M.close() end
  local state = { scope = scope, scope_label = label, origin = origin, typing = typing,
    generation = 0, items = {}, selected = 1, query = '', message = 'Type to search' }
  M.state = state
  state.input, state.results = vim.api.nvim_create_buf(false, true), vim.api.nvim_create_buf(false, true)
  for _, buf in ipairs({ state.input, state.results }) do vim.bo[buf].bufhidden = 'wipe'; vim.bo[buf].filetype = 'jetvim-project-search' end
  state.listwin = vim.api.nvim_open_win(state.results, false, { relative = 'editor', row = 3, col = 1, width = 1, height = 1,
    style = 'minimal', border = 'rounded', focusable = false, zindex = 80 })
  state.promptwin = vim.api.nvim_open_win(state.input, true, { relative = 'editor', row = 0, col = 1, width = 1, height = 1,
    style = 'minimal', border = 'rounded', title = ' Find in Files · ' .. label .. ' ', title_pos = 'left', zindex = 80 })
  for _, win in ipairs({ state.promptwin, state.listwin }) do vim.wo[win].winhighlight = 'Normal:JetvimPopup,NormalFloat:JetvimPopup,FloatBorder:JetvimPopupBorder' end
  vim.wo[state.promptwin].statusline = '%#JetvimStatus#  Find in Files  ›  ' .. label:gsub('%%', '%%%%') .. ' %= Literal search  '
  vim.api.nvim_buf_set_extmark(state.input, ns, 0, 0, { virt_text = { { 'Find › ', 'JetvimMuted' } }, virt_text_pos = 'inline', right_gravity = false })
  require('jetvim.keymap').input_word_delete(state.input)
  for _, mode in ipairs({ 'i', 'n' }) do
    vim.keymap.set(mode, '<Esc>', function() M.close() end, { buffer = state.input, nowait = true })
    vim.keymap.set(mode, '<CR>', M.choose, { buffer = state.input })
    local function bind(key, direction, extend, page, boundary)
      vim.keymap.set(mode, key, function() move(state, direction, extend, page, boundary) end, { buffer = state.input, silent = true })
    end
    bind('<Up>', -1); bind('<Down>', 1)
    bind('<S-Up>', -1, true); bind('<S-Down>', 1, true)
    bind('<PageUp>', -1, false, true); bind('<PageDown>', 1, false, true)
    bind('<S-PageUp>', -1, true, true); bind('<S-PageDown>', 1, true, true)
    bind('<S-Home>', -1, true, false, true); bind('<S-End>', 1, true, false, true)
    bind('<D-S-Up>', -1, true, false, true); bind('<D-S-Down>', 1, true, false, true)
    for index, binding in ipairs(require('jetvim.keymap').bindings or {}) do
      if binding.id == 'select_file_start' or binding.id == 'select_file_end' then
        bind(vim.fn.nr2char(0xF0000 + index), binding.id == 'select_file_start' and -1 or 1, true, false, true)
      end
    end
  end
  local group = vim.api.nvim_create_augroup('JetvimProjectSearch', { clear = true })
  vim.api.nvim_create_autocmd({ 'TextChangedI', 'TextChanged' }, { group = group, buffer = state.input, callback = function() M.change() end })
  vim.api.nvim_create_autocmd('VimResized', { group = group, callback = M.geometry })
  vim.api.nvim_create_autocmd('WinClosed', { group = group, callback = function()
    vim.schedule(function() if alive(state) and (not valid(state.promptwin) or not valid(state.listwin)) then M.close() end end)
  end })
  M.geometry(); draw(state); vim.cmd.startinsert()
end
return M
