local M = { expanded = {}, rows = {}, query = '', matches = {} }
local search_ns = vim.api.nvim_create_namespace('JetvimTreeSearch')
local decoration_ns = vim.api.nvim_create_namespace('JetvimTreeDecorations')
local function valid(win) return win and vim.api.nvim_win_is_valid(win) end
local function in_current_tab(win)
  return valid(win) and vim.api.nvim_win_get_tabpage(win) == vim.api.nvim_get_current_tabpage()
end
local function tree_window(win)
  return in_current_tab(win) and M.buf and vim.api.nvim_buf_is_valid(M.buf)
    and vim.api.nvim_win_get_buf(win) == M.buf and vim.bo[M.buf].filetype == 'jetvim-tree'
end
M.is_tree_window = tree_window
function M.find_tree()
  if tree_window(M.win) then return M.win end
  for _, win in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
    if tree_window(win) then M.win = win; return win end
  end
end
local function editor_buffer(buf)
  return vim.bo[buf].buftype == '' or vim.b[buf].jetvim_editor_placeholder == true
end
function M.is_editor_window(win)
  return in_current_tab(win) and not tree_window(win) and vim.api.nvim_win_get_config(win).relative == ''
    and editor_buffer(vim.api.nvim_win_get_buf(win))
end
function M.find_editor()
  if M.is_editor_window(M.editor_win) then return M.editor_win end
  for _, win in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
    if M.is_editor_window(win) then M.editor_win = win; return win end
  end
end
function M.remember_width()
  local win = M.find_tree()
  if win and M.find_editor() then
    local layout = require('jetvim.layout')
    layout.capture()
    M.sidebar_width = layout.get('tree_width', M.sidebar_width or 30)
  end
end
function M.placeholder()
  local buf = vim.api.nvim_create_buf(false, true)
  vim.b[buf].jetvim_editor_placeholder = true
  vim.bo[buf].bufhidden = 'wipe'
  vim.bo[buf].filetype = 'jetvim-empty'
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, {
    '', '    No files open', '', '    ⌘⇧O  Go to File', '    ⌘1   Project tree',
  })
  vim.bo[buf].modifiable = false
  vim.bo[buf].modified = false
  return buf
end
local function display_name(name)
  return name:gsub('\r', '␍'):gsub('\n', '↵'):gsub('\t', '⇥')
end
function M.window_style(active)
  if not tree_window(M.win) then return end
  local cursorline = active and 'JetvimTreeCursorLine' or 'JetvimTreeCursorLineInactive'
  vim.wo[M.win].winhighlight = 'Normal:JetvimTreeNormal,NormalNC:JetvimTreeNormal,CursorLine:' .. cursorline
    .. ',EndOfBuffer:JetvimTreeNormal,WinSeparator:JetvimSeparator'
end
local function sync_window_style()
  -- Startup creates the sidebar inside VimEnter, where nested WinLeave events
  -- are suppressed. Synchronize after that caller restores editor focus.
  vim.schedule(function()
    if tree_window(M.win) then M.window_style(vim.api.nvim_get_current_win() == M.win) end
  end)
end
function M.update_search(select_match)
  if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
  vim.api.nvim_buf_clear_namespace(M.buf, search_ns, 0, -1)
  M.matches = {}
  if M.query ~= '' then
    for row = 2, vim.api.nvim_buf_line_count(M.buf) do
      local entry = M.rows[row]
      if entry then
        local name = entry.label or entry.name
        local result = vim.fn.matchfuzzypos({ vim.fn.tolower(name) }, vim.fn.tolower(M.query))
        if #result[1] > 0 then
          M.matches[#M.matches + 1] = row
          for _, index in ipairs(result[2][1]) do
            local first = entry.column + vim.fn.byteidx(name, index)
            local last = entry.column + vim.fn.byteidx(name, index + 1)
            vim.api.nvim_buf_set_extmark(M.buf, search_ns, row - 1, first, { end_col = last, hl_group = 'JetvimTreeSearch', priority = 200 })
          end
        end
      end
    end
  end
  vim.bo[M.buf].modifiable = true
  local header = M.query ~= '' and ('  Search [' .. #M.matches .. ']: ' .. M.query) or ''
  vim.api.nvim_buf_set_lines(M.buf, 2, 3, false, { header })
  vim.bo[M.buf].modifiable = false
  vim.bo[M.buf].modified = false
  if M.query ~= '' and #M.matches == 0 then
    vim.api.nvim_buf_set_extmark(M.buf, search_ns, 2, 0, { end_col = #header, hl_group = 'WarningMsg' })
  end
  if select_match and #M.matches > 0 and tree_window(M.win) then
    local current = vim.api.nvim_win_get_cursor(M.win)[1]
    if not vim.tbl_contains(M.matches, current) then vim.api.nvim_win_set_cursor(M.win, { M.matches[1], 0 }) end
  end
end
function M.type_search(text)
  M.query = M.query .. text
  M.update_search(true)
end
function M.clear_search()
  M.query = ''
  M.update_search(false)
end
function M.search_backspace()
  M.query = vim.fn.strcharpart(M.query, 0, math.max(0, vim.fn.strchars(M.query) - 1))
  M.update_search(true)
end
function M.move(direction)
  if not valid(M.win) then return end
  local row = vim.api.nvim_win_get_cursor(M.win)[1]
  if M.query ~= '' then
    if #M.matches == 0 then return end
    local index
    for i, match in ipairs(M.matches) do if match == row then index = i; break end end
    index = index and ((index - 1 + direction) % #M.matches + 1) or (direction == 1 and 1 or #M.matches)
    vim.api.nvim_win_set_cursor(M.win, { M.matches[index], 0 })
  else
    local rows, index = {}, 1
    for visible_row in pairs(M.rows) do rows[#rows + 1] = visible_row end
    table.sort(rows)
    for i, visible_row in ipairs(rows) do if visible_row == row then index = i; break end end
    if #rows > 0 then vim.api.nvim_win_set_cursor(M.win, { rows[math.max(1, math.min(#rows, index + direction))], 0 }) end
  end
end
local function select_row(row)
  vim.api.nvim_win_set_cursor(M.win, { row, 0 })
  if M.query ~= '' and not vim.tbl_contains(M.matches, row) then M.clear_search() end
end
function M.right()
  local row = vim.api.nvim_win_get_cursor(M.win)[1]
  local entry = M.rows[row]
  if not entry or not entry.directory then return end
  if not M.expanded[entry.path] then
    M.expanded[entry.path] = true
    M.render()
  else
    local child_row = entry.root and 4 or row + 1
    local child = M.rows[child_row]
    if child and child.parent == entry.path then select_row(child_row) end
  end
end
function M.left()
  local entry = M.rows[vim.api.nvim_win_get_cursor(M.win)[1]]
  if not entry then return end
  if entry.directory and M.expanded[entry.path] then
    M.expanded[entry.path] = false
    M.render()
  else
    for row, parent in pairs(M.rows) do
      if parent.path == entry.parent then select_row(row); break end
    end
  end
end
function M.editor()
  M.find_tree()
  local win = M.find_editor()
  if win then
    M.remember_width()
    vim.api.nvim_set_current_win(win)
    require('jetvim.layout').rebase()
    return win
  end
  local sidebar_width = require('jetvim.layout').get('tree_width', M.sidebar_width or 30)
  require('jetvim.layout').begin()
  if tree_window(M.win) then vim.api.nvim_set_current_win(M.win) end
  vim.cmd('rightbelow vnew')
  M.editor_win = vim.api.nvim_get_current_win()
  -- A recovery split made beside the tree must use editor options, not inherit
  -- the tree's fixed width and panel colors.
  vim.wo.winfixwidth = false
  vim.wo.winhighlight = ''
  vim.wo.number = vim.go.number
  vim.wo.relativenumber = vim.go.relativenumber
  vim.wo.signcolumn = vim.go.signcolumn
  if tree_window(M.win) then
    vim.api.nvim_win_set_width(M.win, math.min(sidebar_width, math.max(1, vim.o.columns - 12)))
    require('jetvim.layout').attach('tree_width', M.win)
  end
  require('jetvim.layout').finish()
  M.remember_width()
  return M.editor_win
end
function M.render()
  if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
  local selected = tree_window(M.win) and M.rows[vim.api.nvim_win_get_cursor(M.win)[1]] or nil
  local selected_path = selected and selected.path
  local root = require('jetvim.project').root
  if M.expanded[root] == nil then M.expanded[root] = true end
  local icons = require('jetvim.icons')
  local vcs, theme = require('jetvim.vcs'), require('jetvim.theme')
  local root_icon = icons.for_path(root, true, M.expanded[root])
  local root_marker = M.expanded[root] and '▾ ' or '▸ '
  local root_prefix = '  ' .. root_marker .. root_icon.text .. ' '
  local root_name = vim.fs.basename(root)
  local root_label = display_name(root_name)
  local lines = { '  Project', root_prefix .. root_label, '' }
  M.rows = { [2] = { path = root, parent = nil, root = true, directory = true,
    name = root_name, label = root_label, column = #root_prefix } }
  local decorations = {
    { row = 0, first = 0, last = #lines[1], group = 'JetvimTreeTitle' },
    { row = 1, first = 2, last = 2 + #root_marker, group = 'JetvimTreeArrow' },
    { row = 1, first = 2 + #root_marker, last = #root_prefix, group = root_icon.hl },
    { row = 1, first = #root_prefix, last = #lines[2], group = 'JetvimTreeName' },
  }
  local function walk(dir, depth)
    local scan = vim.uv.fs_scandir(dir)
    if not scan then return end
    local entries = {}
    while true do
      local name, kind = vim.uv.fs_scandir_next(scan)
      if not name then break end
      if name ~= '.git' and name ~= '.jetvim' then entries[#entries + 1] = { name = name, kind = kind } end
    end
    table.sort(entries, function(a, b)
      if (a.kind == 'directory') ~= (b.kind == 'directory') then return a.kind == 'directory' end
      return a.name:lower() < b.name:lower()
    end)
    for _, entry in ipairs(entries) do
      local path = dir .. '/' .. entry.name
      local directory = entry.kind == 'directory'
      local marker = directory and (M.expanded[path] and '▾ ' or '▸ ') or '  '
      local icon = icons.for_path(path, directory, M.expanded[path])
      local indent = '  ' .. string.rep('  ', depth)
      local prefix = indent .. marker .. icon.text .. ' '
      local label = display_name(entry.name)
      lines[#lines + 1] = prefix .. label
      M.rows[#lines] = { path = path, parent = dir, directory = directory, name = entry.name, label = label, column = #prefix }
      decorations[#decorations + 1] = { row = #lines - 1, first = #indent, last = #indent + #marker, group = 'JetvimTreeArrow' }
      decorations[#decorations + 1] = { row = #lines - 1, first = #indent + #marker, last = #prefix, group = icon.hl }
      local name_group = directory and 'JetvimTreeName' or theme.filename_group(vcs.status(path))
      decorations[#decorations + 1] = { row = #lines - 1, first = #prefix, last = #lines[#lines], group = name_group }
      if directory and M.expanded[path] then walk(path, depth + 1) end
    end
  end
  if M.expanded[root] then walk(root, 1) end
  vim.bo[M.buf].modifiable = true
  vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
  vim.bo[M.buf].modifiable = false
  vim.api.nvim_buf_clear_namespace(M.buf, decoration_ns, 0, -1)
  for _, mark in ipairs(decorations) do
    vim.api.nvim_buf_set_extmark(M.buf, decoration_ns, mark.row, mark.first, { end_col = mark.last, hl_group = mark.group, priority = 100 })
  end
  if selected_path and tree_window(M.win) then
    for row, entry in pairs(M.rows) do
      if entry.path == selected_path then vim.api.nvim_win_set_cursor(M.win, { row, 0 }); break end
    end
  end
  M.update_search(M.query ~= '')
end
function M.open_entry()
  local entry = M.rows[vim.api.nvim_win_get_cursor(0)[1]]
  if not entry then return end
  if M.query ~= '' and not vim.tbl_contains(M.matches, vim.api.nvim_win_get_cursor(0)[1]) then return end
  M.clear_search()
  if entry.directory then M.expanded[entry.path] = not M.expanded[entry.path]; M.render()
  else require('jetvim.project').open(entry.path) end
end
function M.hide()
  M.clear_search()
  if M.find_tree() then
    M.editor()
    require('jetvim.layout').begin()
    require('jetvim.layout').detach('tree_width')
    if #vim.api.nvim_tabpage_list_wins(0) > 1 then vim.api.nvim_win_close(M.win, true) end
    require('jetvim.layout').finish()
    if vim.bo.buftype == '' and vim.bo.modifiable then vim.cmd.startinsert() end
  end
end
function M.toggle()
  local win = M.find_tree()
  if win and vim.api.nvim_get_current_win() == win then M.hide()
  else M.focus() end
end
function M.focus()
  vim.cmd.stopinsert()
  if M.find_tree() then
    vim.api.nvim_set_current_win(M.win)
    require('jetvim.layout').rebase()
    M.window_style(true)
    sync_window_style()
    require('jetvim.vcs').refresh()
    return
  end
  if vim.bo.buftype == '' then M.editor_win = vim.api.nvim_get_current_win()
  elseif vim.bo.buftype == 'nofile' and vim.bo.filetype == '' and vim.api.nvim_buf_get_name(0) == '' then
    -- The startup welcome screen occupies the editor slot even before a file
    -- has been opened. It is never a tool window.
    vim.b.jetvim_editor_placeholder = true
    M.editor_win = vim.api.nvim_get_current_win()
  end
  require('jetvim.layout').begin()
  M.buf = vim.api.nvim_create_buf(false, true)
  M.query, M.matches = '', {}
  vim.bo[M.buf].bufhidden = 'wipe'
  vim.bo[M.buf].filetype = 'jetvim-tree'
  M.sidebar_width = require('jetvim.layout').get('tree_width', M.sidebar_width or 30)
  vim.cmd('topleft ' .. math.min(M.sidebar_width, math.max(1, vim.o.columns - 12)) .. 'vsplit')
  M.win = vim.api.nvim_get_current_win()
  vim.api.nvim_win_set_buf(M.win, M.buf)
  vim.wo.number = false
  vim.wo.relativenumber = false
  vim.wo.signcolumn = 'no'
  vim.wo.cursorline = true
  vim.wo.winfixwidth = true
  vim.wo.wrap = false
  M.window_style(true)
  vim.opt_local.fillchars:append({ eob = ' ' })
  local function map(key, fn) vim.keymap.set('n', key, fn, { buffer = M.buf, silent = true, nowait = true }) end
  for code = 32, 126 do
    local char = string.char(code)
    map(char == '<' and '<lt>' or char, function() M.type_search(char) end)
  end
  -- A terminal can deliver several typed keys in one chunk. In that case Vim
  -- may resolve an already-complete global leader chord before the single
  -- Space mapping, even with nowait. Shadow those chords with their literal
  -- search text so filenames such as "space name" never navigate the editor.
  for _, binding in ipairs(require('jetvim.keymap').bindings or {}) do
    if binding.fallback then
      local text = binding.fallback:gsub('<leader>', ' ')
      map(binding.fallback, function() M.type_search(text) end)
    end
  end
  map('<CR>', M.open_entry)
  map('<2-LeftMouse>', M.open_entry)
  map('<Down>', function() M.move(1) end)
  map('<Up>', function() M.move(-1) end)
  map('<BS>', M.search_backspace)
  map('<C-h>', M.search_backspace)
  map('<Right>', M.right)
  map('<Left>', M.left)
  map('<Esc>', function()
    if M.query ~= '' then M.clear_search()
    else M.editor(); if vim.bo.modifiable then vim.cmd.startinsert() end end
  end)
  map('<S-Esc>', M.hide)
  map('<Insert>', M.new_file)
  -- On Mac keyboards the key labelled Delete is Backspace. Its shared action
  -- is contextual; forward Delete is an additional native tree-only alias.
  map('<D-Del>', M.delete_entry)
  map('<F5>', function() M.render(); require('jetvim.vcs').refresh() end)
  vim.api.nvim_create_autocmd('BufLeave', { buffer = M.buf, callback = M.clear_search })
  vim.api.nvim_create_autocmd('WinEnter', { buffer = M.buf, callback = function() M.window_style(true) end })
  vim.api.nvim_create_autocmd('WinLeave', { buffer = M.buf, callback = function() M.window_style(false) end })
  M.render()
  vim.api.nvim_win_set_cursor(M.win, { 2, 0 })
  sync_window_style()
  require('jetvim.layout').attach('tree_width', M.win)
  require('jetvim.layout').finish()
  M.remember_width()
  require('jetvim.vcs').refresh()
end
local function within(path, root)
  return root == '/' or path == root or path:sub(1, #root + 1) == root .. '/'
end
local function deletion_path(path, root)
  if type(path) ~= 'string' or path:sub(1, 1) ~= '/' then return end
  path = vim.fs.normalize(path)
  if path == root or not within(path, root) then return end
  local parent = vim.fs.dirname(path)
  -- Resolve the parent, not the entry: a symlink itself may safely be unlinked
  -- even when its target is outside the project.
  if vim.uv.fs_realpath(root) ~= root or vim.uv.fs_realpath(parent) ~= parent then return end
  return path
end
local function identity(a, b)
  return a and b and a.dev == b.dev and a.ino == b.ino and a.type == b.type
end
local function deletion_nodes(path, root, nodes)
  if not deletion_path(path, root) then error('Path must stay inside the project') end
  local stat, err = vim.uv.fs_lstat(path)
  if not stat then error(err or 'File is no longer available') end
  if stat.type == 'directory' then
    local scan, failure = vim.uv.fs_scandir(path)
    if not scan then error(failure or 'Cannot read directory') end
    while true do
      local name = vim.uv.fs_scandir_next(scan)
      if not name then break end
      deletion_nodes(path .. '/' .. name, root, nodes)
    end
  end
  nodes[#nodes + 1] = { path = path, stat = stat }
end
local function affected_buffers(path, directory)
  local buffers = {}
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    local name = vim.api.nvim_buf_get_name(buf)
    -- Do not resolve aliases: unlinking a symlink must not close its target.
    if name == path or directory and within(name, path) then buffers[#buffers + 1] = buf end
  end
  return buffers
end
local function deletable_buffers(buffers)
  local hooks = package.loaded['jetvim.hooks']
  for _, buf in ipairs(buffers) do
    if vim.bo[buf].modified then error('Save or discard unsaved changes before deleting') end
    if vim.b[buf].jetvim_hook_running or hooks and hooks.states[buf] then
      error('Wait for the file save hook to finish before deleting')
    end
  end
end
local function close_deleted_buffers(buffers)
  local deleted, replacement = {}, nil
  for _, buf in ipairs(buffers) do
    if vim.api.nvim_buf_is_valid(buf) and not vim.uv.fs_lstat(vim.api.nvim_buf_get_name(buf)) then deleted[buf] = true end
  end
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    if not deleted[buf] and vim.bo[buf].buflisted and vim.bo[buf].buftype == '' then replacement = buf; break end
  end
  M.remember_width()
  for buf in pairs(deleted) do
    -- Autocommands can edit a buffer while another editor window is replaced.
    -- Preserve such edits rather than force-discarding them after disk deletion.
    if not vim.bo[buf].modified then
      for _, win in ipairs(vim.fn.win_findbuf(buf)) do
        replacement = replacement or M.placeholder()
        vim.api.nvim_win_set_buf(win, replacement)
      end
      if not vim.bo[buf].modified then vim.api.nvim_buf_delete(buf, { force = true }) end
    end
  end
end
function M.delete_entry()
  if M.deleting or not tree_window(vim.api.nvim_get_current_win()) then return end
  local origin, row = vim.api.nvim_get_current_win(), vim.api.nvim_win_get_cursor(0)[1]
  local entry = M.rows[row]
  if not entry or entry.root then return end
  local root = require('jetvim.project').root
  local path = deletion_path(entry.path, root)
  if not path then vim.notify('Path must stay inside the project', vim.log.levels.WARN); return end
  local held, buffers, nodes = {}, {}, {}
  local function hold_buffers(values)
    for _, buf in ipairs(values) do
      if not held[buf] then
        held[buf] = { closing = vim.b[buf].jetvim_closing }
        vim.b[buf].jetvim_closing = true
      end
    end
  end
  M.deleting = true
  local ok, err = pcall(function()
    deletion_nodes(path, root, nodes)
    local directory = nodes[#nodes].stat.type == 'directory'
    buffers = affected_buffers(path, directory)
    deletable_buffers(buffers)
    hold_buffers(buffers)
    local label = display_name(path:sub(root == '/' and 2 or #root + 2))
    local prompt = 'Permanently delete ' .. (directory and 'folder ' or 'file ') .. label
      .. (directory and ' and all its contents?' or '?') .. '\nThis cannot be undone.'
    if vim.fn.confirm(prompt, '&Delete\n&Cancel', 2) ~= 1 then return end
    if require('jetvim.project').root ~= root then error('Project changed; deletion cancelled') end
    buffers = affected_buffers(path, directory)
    deletable_buffers(buffers)
    hold_buffers(buffers)
    -- Nothing may have been replaced or modified while confirmation was open.
    for _, node in ipairs(nodes) do
      local current = deletion_path(node.path, root) and vim.uv.fs_lstat(node.path)
      if not identity(current, node.stat) or current.size ~= node.stat.size
        or not vim.deep_equal(current.mtime, node.stat.mtime)
        or not vim.deep_equal(current.ctime, node.stat.ctime) then error('File changed; deletion cancelled') end
    end
    local failure
    for _, node in ipairs(nodes) do
      local current = deletion_path(node.path, root) and vim.uv.fs_lstat(node.path)
      if not identity(current, node.stat) then failure = 'File changed during deletion'; break end
      local removed, message
      if current.type == 'directory' then removed, message = vim.uv.fs_rmdir(node.path)
      else removed, message = vim.uv.fs_unlink(node.path) end
      if not removed then failure = message or 'Cannot delete entry'; break end
    end
    close_deleted_buffers(buffers)
    for expanded in pairs(M.expanded) do if within(expanded, path) then M.expanded[expanded] = nil end end
    M.clear_search(); M.render()
    if tree_window(origin) then
      vim.api.nvim_set_current_win(origin)
      local last = vim.api.nvim_buf_line_count(M.buf)
      select_row(math.max(2, math.min(row, last)))
    end
    require('jetvim.vcs').refresh()
    if failure then error(failure) end
  end)
  for buf, previous in pairs(held) do
    if vim.api.nvim_buf_is_valid(buf) then
      vim.b[buf].jetvim_closing = previous.closing
      local autosave = package.loaded['jetvim.autosave']
      if autosave then autosave.schedule(buf) end
    end
  end
  M.deleting = false
  if not ok then vim.notify('Cannot delete: ' .. tostring(err), vim.log.levels.WARN) end
end
function M.new_file()
  if not tree_window(vim.api.nvim_get_current_win()) then return end
  local e = M.rows[vim.api.nvim_win_get_cursor(0)[1]]
  local project = require('jetvim.project')
  local dir = e and (e.directory and e.path or vim.fs.dirname(e.path)) or project.root
  require('jetvim.ui').input('New file (trailing / for directory)', function(name)
    if name:sub(1, 1) == '/' or name:find('[%z\r\n]') then
      vim.notify('Enter a relative file or directory name', vim.log.levels.WARN); return
    end
    local path = project.resolve(dir .. '/' .. name)
    if not path then vim.notify('Path must stay inside the project', vim.log.levels.WARN); return end
    if vim.uv.fs_stat(path) then vim.notify('A file or directory already exists at that path', vim.log.levels.WARN); return end
    local directory = name:sub(-1) == '/'
    local ok, err = pcall(vim.fn.mkdir, directory and path or vim.fs.dirname(path), 'p')
    if not ok then vim.notify('Cannot create directory: ' .. tostring(err), vim.log.levels.WARN); return end
    if directory then
      local created = vim.uv.fs_stat(path)
      if not created or created.type ~= 'directory' then vim.notify('Cannot create directory', vim.log.levels.WARN); return end
    end
    if not directory then
      local fd, failure = vim.uv.fs_open(path, 'wx', 420)
      if not fd then vim.notify('Cannot create file: ' .. tostring(failure), vim.log.levels.WARN); return end
      vim.uv.fs_close(fd)
    end
    local parent = vim.fs.dirname(path)
    while parent and project.resolve(parent) do
      M.expanded[parent] = true
      if parent == project.root then break end
      parent = vim.fs.dirname(parent)
    end
    M.clear_search(); M.render()
    if directory then
      for row, entry in pairs(M.rows) do if entry.path == path then select_row(row); break end end
    else project.open(path) end
    require('jetvim.vcs').refresh()
  end)
end
function M.reveal()
  local path = vim.api.nvim_buf_get_name(0)
  local dir = vim.fs.dirname(path)
  local root = require('jetvim.project').root
  while dir and dir ~= root and require('jetvim.project').resolve(dir) do
    M.expanded[dir] = true; dir = vim.fs.dirname(dir)
  end
  M.focus(); M.render()
  for row, entry in pairs(M.rows) do
    if entry.path == path then vim.api.nvim_win_set_cursor(M.win, { row, 0 }); break end
  end
end
-- Non-ASCII text is not a Vim command. Consume it only in this sidebar; the
-- private Unicode keys used by the terminal bridge retain their own mappings.
vim.on_key(function(key, typed)
  if vim.api.nvim_get_current_buf() ~= M.buf or vim.fn.mode() ~= 'n' or key ~= typed then return end
  if vim.fn.strchars(key) ~= 1 then return end
  local code = vim.fn.char2nr(key)
  if code < 160 or (code > 0xF0000 and code <= 0xF0000 + 4096) then return end
  -- Update the query synchronously so a following ASCII key cannot overtake
  -- this character; buffer/cursor rendering waits until the input hook returns.
  M.query = M.query .. key
  local buf = M.buf
  vim.schedule(function()
    if vim.api.nvim_get_current_buf() == buf and M.buf == buf then M.update_search(true) end
  end)
  return ''
end, search_ns)
vim.api.nvim_create_autocmd('User', { group = vim.api.nvim_create_augroup('JetvimTreeVcs', { clear = true }),
  pattern = 'JetvimVcsChanged', callback = M.render })
vim.api.nvim_create_autocmd('WinResized', { callback = M.remember_width })
return M
