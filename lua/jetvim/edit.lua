local M = { history = {} }
local function escape()
  vim.cmd.stopinsert()
  local mode = vim.fn.mode():sub(1, 1)
  if mode == 'v' or mode == 'V' or mode == 's' or mode == 'S' or mode == '\22' or mode == '\19' then
    vim.cmd.normal({ args = { vim.keycode('<Esc>') }, bang = true })
  end
end
function M.selection()
  local mode = vim.fn.mode():sub(1, 1)
  if mode ~= 'v' and mode ~= 'V' and mode ~= 's' and mode ~= 'S' then return nil end
  local anchor, cursor = vim.fn.getpos('v'), vim.fn.getpos('.')
  local a, b = { anchor[2] - 1, anchor[3] - 1 }, { cursor[2] - 1, cursor[3] - 1 }
  if a[1] > b[1] or (a[1] == b[1] and a[2] > b[2]) then a, b = b, a end
  if mode == 'V' or mode == 'S' then
    a[2] = 0
    b[2] = #(vim.api.nvim_buf_get_lines(0, b[1], b[1] + 1, false)[1] or '')
  end
  return { a[1], a[2], b[1], b[2] }
end
function M.rows()
  local s = M.selection()
  if s then return s[1], s[3] - (s[4] == 0 and s[3] > s[1] and 1 or 0) end
  local row = vim.api.nvim_win_get_cursor(0)[1] - 1
  return row, row
end
function M.duplicate()
  local selection = M.selection()
  if selection then
    local text = vim.api.nvim_buf_get_text(0, selection[1], selection[2], selection[3], selection[4], {})
    escape()
    vim.api.nvim_buf_set_text(0, selection[3], selection[4], selection[3], selection[4], text)
  else
    local first, last = M.rows()
    local lines = vim.api.nvim_buf_get_lines(0, first, last + 1, false)
    vim.api.nvim_buf_set_lines(0, last + 1, last + 1, false, lines)
    vim.api.nvim_win_set_cursor(0, { last + 2, vim.api.nvim_win_get_cursor(0)[2] })
  end
end
function M.delete_line()
  local first, last = M.rows()
  escape()
  vim.api.nvim_buf_set_lines(0, first, last + 1, false, {})
end
function M.move_line(direction)
  local first, last = M.rows()
  if first + direction < 0 or last + direction >= vim.api.nvim_buf_line_count(0) then return end
  local col = vim.api.nvim_win_get_cursor(0)[2]
  escape()
  local lines = vim.api.nvim_buf_get_lines(0, first, last + 1, false)
  local other = vim.api.nvim_buf_get_lines(0, direction == -1 and first - 1 or last + 1,
    direction == -1 and first or last + 2, false)[1]
  if direction == -1 then
    lines[#lines + 1] = other
    vim.api.nvim_buf_set_lines(0, first - 1, last + 1, false, lines)
  else
    table.insert(lines, 1, other)
    vim.api.nvim_buf_set_lines(0, first, last + 2, false, lines)
  end
  vim.api.nvim_win_set_cursor(0, { first + direction + 1, col })
end
function M.comment()
  local first, last = M.rows()
  local comment = vim.bo.commentstring
  if comment == '' or not comment:find('%%s') then
    vim.notify('No comment syntax for this file type', vim.log.levels.WARN); return
  end
  local prefix, suffix = comment:match('^(.-)%%s(.-)$')
  prefix, suffix = vim.trim(prefix), vim.trim(suffix)
  local lines = vim.api.nvim_buf_get_lines(0, first, last + 1, false)
  local all = true
  for _, line in ipairs(lines) do
    if line:match('%S') and vim.trim(line):sub(1, #prefix) ~= prefix then all = false end
  end
  for i, line in ipairs(lines) do
    if line:match('%S') then
      local indent, text = line:match('^(%s*)(.*)$')
      if all then
        text = text:sub(#prefix + 1):gsub('^ ', '')
        if suffix ~= '' and text:sub(-#suffix) == suffix then text = text:sub(1, -#suffix - 1):gsub(' $', '') end
        lines[i] = indent .. text
      else lines[i] = indent .. prefix .. ' ' .. text .. (suffix ~= '' and ' ' .. suffix or '') end
    end
  end
  escape()
  vim.api.nvim_buf_set_lines(0, first, last + 1, false, lines)
end
local function clipboard(text, kind)
  -- Keep a local register even on machines without a clipboard provider.
  vim.fn.setreg('"', text, kind)
  if vim.fn.has('clipboard') == 1 or vim.fn.executable('pbcopy') == 1 then vim.fn.setreg('+', text, kind) end
  table.insert(M.history, 1, { text = vim.deepcopy(text), kind = kind })
  if #M.history > 30 then table.remove(M.history) end
end
function M.copy(cut)
  local selection = M.selection()
  if selection then
    local text = vim.api.nvim_buf_get_text(0, selection[1], selection[2], selection[3], selection[4], {})
    clipboard(text, 'v')
    if cut then
      escape()
      vim.api.nvim_buf_set_text(0, selection[1], selection[2], selection[3], selection[4], {})
      vim.api.nvim_win_set_cursor(0, { selection[1] + 1, selection[2] })
    end
  else
    local first, last = M.rows()
    clipboard(vim.api.nvim_buf_get_lines(0, first, last + 1, false), 'V')
    if cut then M.delete_line() end
  end
end
function M.paste(text, kind)
  if not text then
    local reg = (vim.fn.has('clipboard') == 1 or vim.fn.executable('pbpaste') == 1) and '+' or '"'
    text, kind = vim.fn.getreg(reg, 1, true), vim.fn.getregtype(reg)
  end
  local selection = M.selection()
  if selection then
    escape()
    vim.api.nvim_buf_set_text(0, selection[1], selection[2], selection[3], selection[4], {})
    vim.api.nvim_win_set_cursor(0, { selection[1] + 1, selection[2] })
  end
  if kind == 'V' and not selection then
    local row = vim.api.nvim_win_get_cursor(0)[1] - 1
    vim.api.nvim_buf_set_lines(0, row, row, false, text)
  else
    local cursor = vim.api.nvim_win_get_cursor(0)
    vim.api.nvim_buf_set_text(0, cursor[1] - 1, cursor[2], cursor[1] - 1, cursor[2], text)
    if #text > 0 then
      vim.api.nvim_win_set_cursor(0, { cursor[1] + #text - 1, (#text == 1 and cursor[2] or 0) + #text[#text] })
    end
  end
end
function M.newline(split)
  local pos = vim.api.nvim_win_get_cursor(0)
  local line = vim.api.nvim_get_current_line()
  local indent = line:match('^%s*')
  if split then vim.api.nvim_buf_set_text(0, pos[1] - 1, pos[2], pos[1] - 1, pos[2], { '', indent })
  else vim.api.nvim_buf_set_lines(0, pos[1], pos[1], false, { indent }) end
  vim.api.nvim_win_set_cursor(0, { pos[1] + 1, #indent })
  vim.cmd.startinsert()
end
function M.select_all()
  escape()
  vim.api.nvim_win_set_cursor(0, { 1, 0 })
  vim.cmd.normal({ args = { 'vG$' }, bang = true })
  local row = vim.api.nvim_buf_line_count(0)
  vim.api.nvim_win_set_cursor(0, { row, #(vim.api.nvim_buf_get_lines(0, row - 1, row, false)[1]) })
  vim.cmd.normal({ args = { vim.keycode('<C-g>') }, bang = true })
end
function M.collapse_selection(ending, fallback)
  local selection = M.selection()
  if not selection then
    -- Block Select mode is outside the ordinary typing-selection range helper;
    -- keep its existing native arrow behavior instead of swallowing the key.
    if fallback then vim.api.nvim_feedkeys(vim.keycode(fallback), 'n', false) end
    return
  end
  local target = ending and { selection[3] + 1, selection[4] } or { selection[1] + 1, selection[2] }
  escape()
  vim.api.nvim_win_set_cursor(0, target)
  if vim.bo.modifiable and not vim.bo.readonly
    and (vim.bo.buftype == '' or vim.bo.buftype == 'prompt'
      or vim.bo.filetype == 'jetvim-search' or vim.bo.filetype == 'jetvim-project-search') then
    vim.cmd.startinsert()
  end
end
function M.extend_selection()
  require('jetvim.selection').extend()
end
function M.set_selection(range)
  escape()
  vim.api.nvim_win_set_cursor(0, { range[1] + 1, range[2] })
  vim.cmd.normal({ args = { 'v' }, bang = true })
  vim.api.nvim_win_set_cursor(0, { range[3] + 1, range[4] })
  vim.cmd.normal({ args = { vim.keycode('<C-g>') }, bang = true })
end
function M.shrink_selection()
  require('jetvim.selection').shrink()
end
function M.indent(direction)
  local first, last = M.rows()
  escape()
  vim.cmd(string.format('%d,%d%s', first + 1, last + 1, direction == 1 and '>' or '<'))
end
function M.replace()
  local buf = vim.api.nvim_get_current_buf()
  require('jetvim.ui').input('Find literal text', function(find)
    vim.ui.input({ prompt = 'Replace with: ' }, function(replacement)
      if replacement == nil or not vim.api.nvim_buf_is_valid(buf) then return end
      local count = 0
      vim.api.nvim_buf_call(buf, function()
        local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
        for i, line in ipairs(lines) do
          lines[i] = line:gsub(vim.pesc(find), function() count = count + 1; return replacement end)
        end
        vim.ui.select({ 'Replace ' .. count .. ' occurrences', 'Cancel' }, { prompt = 'Replace in current file?' }, function(choice)
          if choice and choice ~= 'Cancel' then vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines) end
        end)
      end)
    end)
  end)
end
return M
