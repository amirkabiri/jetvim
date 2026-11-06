local M = { rows = {}, generation = 0, preview_generation = 0 }
local highlight_ns = vim.api.nvim_create_namespace('JetvimGitHighlights')
local function valid(win) return win and vim.api.nvim_win_is_valid(win) end
function M.remember_size()
  -- Closing one vertical pane expands the survivor. Only a complete, identified
  -- pair represents the user's chosen list width and bottom-panel height.
  if M.restoring or M.tearing_down or not valid(M.list_win) or not valid(M.diff_win) then return end
  if vim.api.nvim_win_get_buf(M.list_win) ~= M.list_buf or vim.api.nvim_win_get_buf(M.diff_win) ~= M.diff_buf then return end
  if vim.api.nvim_win_get_tabpage(M.list_win) ~= vim.api.nvim_win_get_tabpage(M.diff_win) then return end
  local layout = require('jetvim.layout')
  layout.capture()
  M.size = { height = layout.get('git_height', 14), list_width = layout.get('git_list_width', math.min(42, math.floor(vim.o.columns * 0.35))) }
end
local function restore_size()
  local layout = require('jetvim.layout')
  local preferred = { height = layout.get('git_height', M.size and M.size.height or 14), list_width = layout.get('git_list_width', M.size and M.size.list_width or math.min(42, math.floor(vim.o.columns * 0.35))) }
  local height = math.max(1, math.min(preferred.height, math.max(1, vim.o.lines - vim.o.cmdheight - 6)))
  -- Leave room for the preview and the shared separator in narrow terminals.
  local minimum = math.max(1, math.min(10, math.floor((vim.o.columns - 1) / 2)))
  local width = math.max(minimum, math.min(preferred.list_width, math.max(minimum, vim.o.columns - minimum - 1)))
  vim.api.nvim_win_set_height(M.list_win, height)
  vim.api.nvim_win_set_width(M.list_win, width)
end
local function command(cwd, args, callback)
  local cmd = { 'git', '--no-pager', '--no-optional-locks', '--literal-pathspecs',
    '-c', 'color.ui=false', '-c', 'core.fsmonitor=false', '-C', cwd }
  vim.list_extend(cmd, args)
  -- Porcelain -z paths are byte strings; text mode would rewrite CRLF in names.
  return vim.system(cmd, { timeout = 10000 }, function(result) vim.schedule(function() callback(result) end) end)
end
local function display(path) return path:gsub('\n', '↵'):gsub('\r', ''):gsub('\t', '  ') end
local function set_lines(buf, lines)
  if not buf or not vim.api.nvim_buf_is_valid(buf) then return end
  vim.bo[buf].modifiable = true
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.bo[buf].modifiable = false
  vim.bo[buf].modified = false
  vim.api.nvim_buf_clear_namespace(buf, highlight_ns, 0, -1)
  if #lines > 0 and #lines[1] > 0 then
    vim.api.nvim_buf_set_extmark(buf, highlight_ns, 0, 0, { end_col = #lines[1], hl_group = 'JetvimToolTitle' })
  end
  if buf == M.list_buf and #lines > 1 and #lines[2] > 0 then
    vim.api.nvim_buf_set_extmark(buf, highlight_ns, 1, 0, { end_col = #lines[2], hl_group = 'JetvimMuted' })
  end
end
function M.parse_status(output)
  local fields, entries = vim.split(output, '\0', { plain = true, trimempty = true }), {}
  local i = 1
  while i <= #fields do
    local field = fields[i]
    local x, y, path = field:sub(1, 1), field:sub(2, 2), field:sub(4)
    local old
    if x == 'R' or x == 'C' or y == 'R' or y == 'C' then i = i + 1; old = fields[i] end
    local function add(section, status)
      entries[#entries + 1] = { section = section, status = status, path = path, old = old }
    end
    if x == '?' and y == '?' then add('Untracked Files', '?')
    elseif x == 'U' or y == 'U' or x .. y == 'AA' or x .. y == 'DD' then add('Conflicts', x .. y)
    else
      if x ~= ' ' then add('Staged Changes', x) end
      if y ~= ' ' then add('Unstaged Changes', y) end
    end
    i = i + 1
  end
  return entries
end
function M.preview()
  if not valid(M.list_win) or not valid(M.diff_win) then return end
  local entry = M.rows[vim.api.nvim_win_get_cursor(M.list_win)[1]]
  M.preview_generation = M.preview_generation + 1
  local generation, buf = M.preview_generation, M.diff_buf
  if not entry then set_lines(buf, { ' Select a changed file to preview its diff.' }); return end
  local absolute = M.repo .. '/' .. entry.path
  if not require('jetvim.project').resolve(absolute) then
    set_lines(buf, { ' File is outside the selected project.' }); return
  end
  set_lines(buf, { ' ' .. entry.section .. ' · ' .. display(entry.path), '', ' Loading diff…' })
  local args = { 'diff', '--no-ext-diff', '--no-textconv' }
  if entry.section == 'Staged Changes' then args[#args + 1] = '--cached' end
  if entry.section == 'Untracked Files' then
    vim.list_extend(args, { '--no-index', '--', '/dev/null', absolute })
  else
    vim.list_extend(args, { '--', entry.path })
    if entry.old then args[#args + 1] = entry.old end
  end
  command(M.repo, args, function(result)
    if generation ~= M.preview_generation or not valid(M.diff_win) or M.diff_buf ~= buf then return end
    local lines = { ' ' .. entry.section .. ' · ' .. display(entry.path), '' }
    if result.code ~= 0 and result.code ~= 1 then
      vim.list_extend(lines, vim.split(result.stderr or 'Git diff failed', '\n', { trimempty = true }))
    elseif result.stdout == '' then lines[#lines + 1] = ' No textual changes (or a binary/submodule change).'
    else vim.list_extend(lines, vim.split(result.stdout, '\n', { trimempty = false })) end
    set_lines(buf, lines)
    vim.api.nvim_win_set_cursor(M.diff_win, { 1, 0 })
  end)
end
function M.render(entries)
  local selected = valid(M.list_win) and M.rows[vim.api.nvim_win_get_cursor(M.list_win)[1]] or nil
  local lines = { ' GIT · Local Changes', ' Enter open · R refresh · Esc editor', '' }
  M.rows = {}
  for _, section in ipairs({ 'Conflicts', 'Staged Changes', 'Unstaged Changes', 'Untracked Files' }) do
    local group = {}
    for _, entry in ipairs(entries) do if entry.section == section then group[#group + 1] = entry end end
    if #group > 0 then
      lines[#lines + 1] = ' ▾ ' .. section .. ' (' .. #group .. ')'
      for _, entry in ipairs(group) do
        lines[#lines + 1] = '   ' .. entry.status .. ' ' .. display(entry.path)
        M.rows[#lines] = entry
      end
      lines[#lines + 1] = ''
    end
  end
  if #entries == 0 then lines[#lines + 1] = ' Working tree clean.' end
  set_lines(M.list_buf, lines)
  for row, entry in pairs(M.rows) do
    local group = entry.status:find('D', 1, true) and 'JetvimGitDeleted'
      or ((entry.status == 'A' or entry.status == '?') and 'JetvimGitAdded' or 'JetvimGitChanged')
    vim.api.nvim_buf_set_extmark(M.list_buf, highlight_ns, row - 1, 3, { end_col = #lines[row], hl_group = group })
  end
  for row, line in ipairs(lines) do
    if line:find(' ▾ ', 1, true) == 1 then
      vim.api.nvim_buf_set_extmark(M.list_buf, highlight_ns, row - 1, 0, { end_col = #line, hl_group = 'JetvimToolTitle' })
    end
  end
  local target
  for row = 4, #lines do
    local entry = M.rows[row]
    if entry then
      target = target or row
      if selected and selected.path == entry.path and selected.section == entry.section then target = row; break end
    end
  end
  if target and valid(M.list_win) then vim.api.nvim_win_set_cursor(M.list_win, { target, 0 }) end
  M.preview()
end
function M.refresh()
  if not valid(M.list_win) then return end
  M.generation = M.generation + 1
  M.preview_generation = M.preview_generation + 1
  local generation = M.generation
  if vim.fn.executable('git') ~= 1 then
    M.rows = {}; set_lines(M.list_buf, { ' Git is not installed.' }); set_lines(M.diff_buf, { '' }); return
  end
  local project = require('jetvim.project').root
  command(project, { 'rev-parse', '--show-toplevel' }, function(root)
    if generation ~= M.generation or not valid(M.list_win) then return end
    if root.code ~= 0 then
      M.rows = {}
      set_lines(M.list_buf, { ' GIT · Local Changes', '', ' This folder is not in a Git repository.' })
      set_lines(M.diff_buf, { ' Open a project containing a Git repository to see its changes.' })
      return
    end
    M.repo = (root.stdout or ''):gsub('[\r\n]+$', '')
    command(project, { 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--', '.' }, function(result)
      if generation ~= M.generation or not valid(M.list_win) then return end
      if result.code ~= 0 then
        M.rows = {}
        set_lines(M.list_buf, { ' Git status failed.', display(result.stderr or '') })
        set_lines(M.diff_buf, { '' }); return
      end
      M.render(M.parse_status(result.stdout or ''))
    end)
  end)
end
function M.move(direction)
  local current, rows = vim.api.nvim_win_get_cursor(M.list_win)[1], {}
  for row in pairs(M.rows) do rows[#rows + 1] = row end
  table.sort(rows)
  if #rows == 0 then return end
  local index = 1
  for i, row in ipairs(rows) do if row == current then index = i; break end end
  index = math.max(1, math.min(#rows, index + direction))
  vim.api.nvim_win_set_cursor(M.list_win, { rows[index], 0 })
  M.preview()
end
function M.open_entry()
  local entry = M.rows[vim.api.nvim_win_get_cursor(M.list_win)[1]]
  if not entry then return end
  local path = M.repo .. '/' .. entry.path
  if not vim.uv.fs_stat(path) then vim.notify('This file was deleted; its diff is shown in Git Changes'); return end
  M.editor()
  require('jetvim.tree').editor_win = vim.api.nvim_get_current_win()
  require('jetvim.project').open(path)
end
function M.editor()
  if valid(M.editor_win) then vim.api.nvim_set_current_win(M.editor_win)
  else require('jetvim.tree').editor() end
  if vim.bo.modifiable then vim.cmd.startinsert() end
end
function M.hide()
  M.remember_size()
  require('jetvim.layout').begin()
  require('jetvim.layout').detach('git_height')
  require('jetvim.layout').detach('git_list_width')
  M.tearing_down = true
  M.generation, M.preview_generation = M.generation + 1, M.preview_generation + 1
  M.editor()
  for _, win in ipairs({ M.diff_win, M.list_win }) do
    if valid(win) and #vim.api.nvim_tabpage_list_wins(0) > 1 then vim.api.nvim_win_close(win, true) end
  end
  M.tearing_down = false
  require('jetvim.layout').finish()
end
function M.toggle()
  vim.cmd.stopinsert()
  if valid(M.list_win) and valid(M.diff_win) then
    if vim.api.nvim_get_current_win() == M.list_win or vim.api.nvim_get_current_win() == M.diff_win then M.hide()
    else vim.api.nvim_set_current_win(M.list_win); require('jetvim.layout').rebase(); M.refresh() end
    return
  end
  -- Recover if a pane was closed manually, without leaving an orphaned preview.
  require('jetvim.layout').begin()
  M.tearing_down = true
  for _, win in pairs({ M.diff_win, M.list_win }) do
    if valid(win) and #vim.api.nvim_tabpage_list_wins(0) > 1 then vim.api.nvim_win_close(win, true) end
  end
  M.tearing_down = false
  if vim.bo.buftype == '' then M.editor_win = vim.api.nvim_get_current_win()
  else M.editor_win = require('jetvim.tree').editor_win end
  M.list_buf, M.diff_buf = vim.api.nvim_create_buf(false, true), vim.api.nvim_create_buf(false, true)
  for _, buf in ipairs({ M.list_buf, M.diff_buf }) do vim.bo[buf].bufhidden = 'wipe'; vim.bo[buf].swapfile = false end
  vim.bo[M.list_buf].filetype, vim.bo[M.diff_buf].filetype = 'jetvim-git', 'diff'
  M.restoring = true
  vim.cmd('botright split')
  M.list_win = vim.api.nvim_get_current_win()
  vim.api.nvim_win_set_buf(M.list_win, M.list_buf)
  vim.cmd('rightbelow vsplit')
  M.diff_win = vim.api.nvim_get_current_win()
  vim.api.nvim_win_set_buf(M.diff_win, M.diff_buf)
  restore_size()
  for _, win in ipairs({ M.list_win, M.diff_win }) do
    vim.wo[win].number = false; vim.wo[win].relativenumber = false
    vim.wo[win].signcolumn = 'no'; vim.wo[win].wrap = false
    vim.wo[win].winfixheight = true
    vim.wo[win].winhighlight = 'Normal:JetvimToolNormal,NormalNC:JetvimToolNormal,CursorLine:JetvimToolCursorLine,WinSeparator:JetvimSeparator'
  end
  vim.wo[M.list_win].winfixwidth = true
  vim.wo[M.list_win].cursorline = true
  local function map(buf, key, fn) vim.keymap.set('n', key, fn, { buffer = buf, silent = true, nowait = true }) end
  for _, buf in ipairs({ M.list_buf, M.diff_buf }) do
    map(buf, '<Esc>', M.editor); map(buf, '<S-Esc>', M.hide); map(buf, 'R', M.refresh)
  end
  map(M.list_buf, '<Down>', function() M.move(1) end)
  map(M.list_buf, '<Up>', function() M.move(-1) end)
  map(M.list_buf, '<CR>', M.open_entry)
  map(M.list_buf, '<2-LeftMouse>', M.open_entry)
  map(M.list_buf, '<Tab>', function() vim.api.nvim_set_current_win(M.diff_win) end)
  map(M.diff_buf, '<S-Tab>', function() vim.api.nvim_set_current_win(M.list_win) end)
  vim.api.nvim_create_autocmd('CursorMoved', { buffer = M.list_buf, callback = M.preview })
  vim.api.nvim_create_autocmd('WinResized', { group = vim.api.nvim_create_augroup('JetvimGitSize', { clear = true }), callback = M.remember_size })
  vim.api.nvim_create_autocmd('BufWritePost', { group = vim.api.nvim_create_augroup('JetvimGitRefresh', { clear = true }),
    callback = function() if valid(M.list_win) then M.refresh() end end })
  vim.api.nvim_set_current_win(M.list_win)
  M.restoring = false
  require('jetvim.layout').attach('git_height', M.list_win)
  require('jetvim.layout').attach('git_list_width', M.list_win)
  require('jetvim.layout').finish()
  M.remember_size()
  set_lines(M.diff_buf, { ' Loading Git changes…' })
  M.refresh()
end
return M
