-- A two-action path menu belongs only to the revealed project-tree entry.
local M = {}
local function valid(win) return win and vim.api.nvim_win_is_valid(win) end
local function within(path, root)
  return root == '/' or path == root or path:sub(1, #root + 1) == root .. '/'
end
local function safe_path(path, root)
  return type(path) == 'string' and path:sub(1, 1) == '/' and vim.fs.normalize(path) == path
    and within(path, root) and vim.uv.fs_realpath(root) == root
    and (path == root or vim.uv.fs_realpath(vim.fs.dirname(path)) == vim.fs.dirname(path))
end
function M.close(focus_tree)
  local state = M.state
  if not state then return end
  M.state = nil
  if valid(state.win) then vim.api.nvim_win_close(state.win, true) end
  if focus_tree and state.tree.is_tree_window(state.origin) then vim.api.nvim_set_current_win(state.origin) end
end
function M.open(tree, entry)
  M.close(false)
  local root, path = require('jetvim.project').root, entry and entry.path
  if not safe_path(path, root) or not vim.uv.fs_lstat(path) then return end
  local origin = tree.find_tree()
  if not origin then return end
  local buf = vim.api.nvim_create_buf(false, true)
  vim.bo[buf].bufhidden = 'wipe'
  vim.bo[buf].filetype = 'jetvim-tree-context'
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, { '  Copy Relative Path', '  Copy Absolute Path' })
  vim.bo[buf].modifiable = false
  local row = vim.api.nvim_win_call(origin, vim.fn.winline)
  local ok, win = pcall(vim.api.nvim_open_win, buf, true, {
    relative = 'win', win = origin, row = row, col = 3,
    width = math.max(20, math.min(28, vim.o.columns - 4)), height = 2,
    style = 'minimal', border = 'rounded', title = ' File path ',
    footer = ' Enter copy · Esc close ', footer_pos = 'center',
  })
  if not ok then
    vim.api.nvim_buf_delete(buf, { force = true })
    vim.notify('Cannot open file menu: ' .. tostring(win), vim.log.levels.WARN)
    return
  end
  local state = { tree = tree, origin = origin, root = root, path = path, buf = buf, win = win }
  M.state = state
  vim.wo[win].cursorline = true
  vim.wo[win].winhighlight = 'Normal:JetvimPopup,NormalFloat:JetvimPopup,FloatBorder:JetvimPopupBorder,CursorLine:JetvimPickerSelected'
  local function move(direction)
    if M.state == state and valid(win) then
      local cursor = vim.api.nvim_win_get_cursor(win)[1]
      vim.api.nvim_win_set_cursor(win, { math.max(1, math.min(2, cursor + direction)), 0 })
    end
  end
  local function choose()
    if M.state ~= state then return end
    local selected = vim.api.nvim_win_get_cursor(win)[1]
    local current = tree.is_tree_window(origin) and tree.rows[vim.api.nvim_win_get_cursor(origin)[1]]
    local allowed = require('jetvim.project').root == root and current and current.path == path
      and safe_path(path, root) and vim.uv.fs_lstat(path)
    M.close(true)
    if not allowed then vim.notify('File context changed; path was not copied', vim.log.levels.WARN); return end
    local text = selected == 1 and (path == root and '.' or path:sub(root == '/' and 2 or #root + 2)) or path
    require('jetvim.edit').copy_text(text)
  end
  for _, mode in ipairs({ 'n', 'i' }) do
    vim.keymap.set(mode, '<Esc>', function() M.close(true) end, { buffer = buf, silent = true, nowait = true })
    vim.keymap.set(mode, '<CR>', choose, { buffer = buf, silent = true })
    vim.keymap.set(mode, '<Up>', function() move(-1) end, { buffer = buf, silent = true })
    vim.keymap.set(mode, '<Down>', function() move(1) end, { buffer = buf, silent = true })
  end
  vim.api.nvim_create_autocmd('WinLeave', { buffer = buf, once = true, callback = function()
    vim.schedule(function() if M.state == state then M.close(false) end end)
  end })
  vim.api.nvim_create_autocmd('WinClosed', { pattern = tostring(win), once = true, callback = function()
    vim.schedule(function() if M.state == state then M.close(false) end end)
  end })
end
function M.reveal()
  M.close(true)
  local tree = require('jetvim.tree')
  local entry = tree.reveal()
  if entry then M.open(tree, entry) end
end
return M
