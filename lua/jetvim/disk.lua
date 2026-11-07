-- External writes are observed without forcing away unsaved editor changes.
local M = { states = {}, interval_ms = 500 }
local function path(buf)
  if not vim.api.nvim_buf_is_valid(buf) or not vim.api.nvim_buf_is_loaded(buf)
    or not vim.bo[buf].buflisted or vim.bo[buf].buftype ~= '' then return end
  local name = vim.api.nvim_buf_get_name(buf)
  if name == '' then return end
  local project, settings = require('jetvim.project'), package.loaded['jetvim.settings']
  return project.resolve(name) or project.resolve_tool(name)
    or (settings and settings.allow_path(name) and vim.fn.fnamemodify(name, ':p'))
end
local function stat(file)
  local value = vim.uv.fs_stat(file)
  if not value or value.type ~= 'file' then return false end
  return { dev = value.dev, ino = value.ino, size = value.size, mtime = value.mtime }
end
local function track(buf)
  local file = path(buf)
  if not file then M.states[buf] = nil; return end
  M.states[buf] = { path = file, name = vim.api.nvim_buf_get_name(buf), expected = stat(file) }
end
local function notify(state, current, message)
  if vim.deep_equal(state.notified, { current }) then return end
  state.notified = { current }
  local text = (vim.fs.basename(state.path) .. ': ' .. message):gsub('[\r\n]', ' ')
  while vim.fn.strdisplaywidth(text) > math.max(20, vim.o.columns - 4) do
    text = vim.fn.strcharpart(text, 0, vim.fn.strchars(text) - 1)
  end
  vim.notify(text, vim.log.levels.WARN, { title = 'Jetvim disk changes' })
end
local function busy()
  local mode = vim.api.nvim_get_mode()
  return mode.blocking or mode.mode:match('^[cr]')
end
local function views(buf)
  local result = {}
  for _, win in ipairs(vim.fn.win_findbuf(buf)) do
    if vim.api.nvim_win_is_valid(win) then result[win] = vim.api.nvim_win_call(win, vim.fn.winsaveview) end
  end
  return result
end
local function restore(buf, saved)
  for win, view in pairs(saved) do
    if vim.api.nvim_win_is_valid(win) and vim.api.nvim_win_get_buf(win) == buf then
      vim.api.nvim_win_call(win, function() vim.fn.winrestview(view) end)
    end
  end
end
function M.check(buf)
  if M.stopping or M.reloading or busy() then return end
  local state = M.states[buf]
  local file = path(buf)
  if not file then M.states[buf] = nil; return end
  if not state or state.path ~= file or state.name ~= vim.api.nvim_buf_get_name(buf) then track(buf); return end
  local current = stat(file)
  if vim.deep_equal(current, state.expected) then return end
  if not current then
    notify(state, current, 'deleted on disk; editor contents kept')
    return
  end
  if vim.bo[buf].modified then
    notify(state, current, 'changed on disk; unsaved edits kept. Review before saving.')
    return
  end
  local autosave = package.loaded['jetvim.autosave']
  if vim.b[buf].jetvim_closing or vim.b[buf].jetvim_hook_running or autosave and autosave.writing then return end
  local saved = views(buf)
  local readonly, confirm, previous_error = vim.bo[buf].readonly, vim.o.confirm, vim.v.errmsg
  local writing = autosave and autosave.writing
  -- nvim_buf_call can temporarily switch buffers. Those internal transitions
  -- must not save a different dirty file through focus-leave autosave.
  if autosave then autosave.writing = true end
  M.reloading, vim.o.confirm, vim.v.errmsg = true, false, ''
  local ok, err = pcall(vim.api.nvim_buf_call, buf, function()
    if vim.bo.modified then error('Buffer changed before reload') end
    -- No bang: a late modification can never be discarded by this command.
    vim.cmd('silent keepalt edit')
  end)
  local read_error = vim.v.errmsg
  M.reloading, vim.o.confirm, vim.v.errmsg = false, confirm, previous_error
  if autosave then autosave.writing = writing end
  if vim.api.nvim_buf_is_valid(buf) then
    if readonly then vim.bo[buf].readonly = true end
    restore(buf, saved)
  end
  if not ok or read_error ~= '' then
    notify(state, current, 'cannot reload: ' .. tostring(not ok and err or read_error))
    return
  end
  -- BufReadPost records the actual fresh snapshot, including autosave's expected
  -- disk version. Other read observers refresh syntax, LSP and line annotations.
  if M.states[buf] then M.states[buf].notified = nil end
  -- Save-hook diagnostics describe the previous saved version. Language-server
  -- namespaces stay intact while their clients process the native buffer edit.
  local api = package.loaded['jetvim.api']
  for source, ns in pairs(api and api.namespaces or {}) do
    if source:sub(1, 5) == 'hook:' then vim.diagnostic.reset(ns, buf) end
  end
  local vcs = package.loaded['jetvim.vcs']
  if vcs then vcs.refresh() end
  local overview = package.loaded['jetvim.overview']
  if overview then overview.schedule() end
  vim.api.nvim_exec_autocmds('User', { pattern = 'JetvimDiskChanged', modeline = false, data = { buffer = buf, file = file } })
end
-- Explicit formatter checks may use native reload while automatic timestamp
-- events are deferred. The scope is synchronous and never permits dirty reads.
function M.with_native_reload(buf, callback)
  buf = (not buf or buf == 0) and vim.api.nvim_get_current_buf() or buf
  assert(path(buf) and not vim.bo[buf].modified and not vim.b[buf].jetvim_closing, 'Cannot reload a dirty or unavailable buffer')
  local previous, autosave = M.native_reload, package.loaded['jetvim.autosave']
  local writing = autosave and autosave.writing
  M.native_reload = buf
  if autosave then autosave.writing = true end
  local ok, result = pcall(callback)
  M.native_reload = previous
  if autosave then autosave.writing = writing end
  if not ok then error(result, 0) end
  return result
end
-- The save pipeline calls this only after verifying exact clean buffer/disk
-- bytes. Recheck the verified stat so a newer external write is not adopted.
function M.acknowledge(buf, expected)
  buf = (not buf or buf == 0) and vim.api.nvim_get_current_buf() or buf
  local file = path(buf)
  if not file or vim.bo[buf].modified or type(expected) ~= 'table' then return false end
  local current = stat(file)
  if not current or not vim.deep_equal(current, expected) then return false end
  M.states[buf] = { path = file, name = vim.api.nvim_buf_get_name(buf), expected = current }
  return true
end
function M.scan()
  if M.stopping or busy() then return end
  for _, buf in ipairs(vim.tbl_keys(M.states)) do M.check(buf) end
end
function M.schedule()
  if M.pending or M.stopping then return end
  M.pending = true
  vim.schedule(function() M.pending = false; M.scan() end)
end
-- Carry the original observed version across a verified filesystem rename.
function M.rebind(buf, previous)
  if not previous or not vim.api.nvim_buf_is_valid(buf) then return end
  track(buf)
  local state = M.states[buf]
  if not state then return end
  state.expected, state.notified = previous.expected, previous.notified
end
function M.setup()
  M.stopping = false
  local group = vim.api.nvim_create_augroup('JetvimDiskChanges', { clear = true })
  vim.api.nvim_create_autocmd({ 'BufReadPost', 'BufWritePost', 'BufNewFile', 'BufFilePost' }, { group = group, callback = function(event) track(event.buf) end })
  vim.api.nvim_create_autocmd('BufEnter', { group = group, callback = function(event)
    if not M.states[event.buf] then track(event.buf) end
    M.schedule()
  end })
  vim.api.nvim_create_autocmd('FocusGained', { group = group, callback = M.schedule })
  -- Native timestamp checks can otherwise display a blocking conflict dialog.
  -- Keep our guarded, scheduled reload/notice path for files owned by Jetvim.
  vim.api.nvim_create_autocmd('FileChangedShell', { group = group, callback = function(event)
    if path(event.buf) then
      if M.native_reload == event.buf and not vim.bo[event.buf].modified and not vim.b[event.buf].jetvim_closing then
        vim.v.fcs_choice = 'reload'
      else vim.v.fcs_choice = ''; M.schedule() end
    end
  end })
  vim.api.nvim_create_autocmd({ 'BufUnload', 'BufWipeout' }, { group = group, callback = function(event) M.states[event.buf] = nil end })
  vim.api.nvim_create_autocmd('VimLeavePre', { group = group, callback = function()
    M.stopping = true
    if M.timer and not M.timer:is_closing() then M.timer:stop(); M.timer:close() end
  end })
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do track(buf) end
  if M.timer and not M.timer:is_closing() then M.timer:stop(); M.timer:close() end
  M.timer = vim.uv.new_timer()
  M.timer:unref()
  M.timer:start(M.interval_ms, M.interval_ms, vim.schedule_wrap(M.schedule))
end
return M
