-- Debounced idle writes and optional focus-leave writes; never force conflicts.
local M = { states = {} }
local function stopped() return M.exiting or vim.env.JETVIM_DISABLE_AUTOSAVE == '1' or not require('jetvim.settings').get().autosave.enabled end
local function stat(path)
  local value = vim.uv.fs_stat(path)
  if not value then return false end
  return { dev = value.dev, ino = value.ino, size = value.size, mtime = value.mtime }
end
local function path(buf)
  if not vim.api.nvim_buf_is_valid(buf) or not vim.api.nvim_buf_is_loaded(buf) then return end
  if vim.bo[buf].buftype ~= '' or not vim.bo[buf].buflisted then return end
  local name = vim.api.nvim_buf_get_name(buf)
  if name == '' then return end
  local project = require('jetvim.project')
  return project.resolve(name) or project.resolve_tool(name)
    or (require('jetvim.settings').allow_path(name) and vim.fn.fnamemodify(name, ':p'))
end
local function stop(state)
  if state and state.timer and not state.timer:is_closing() then state.timer:stop() end
end
local function track(buf, read)
  local name = path(buf)
  if not name then return end
  local state = M.states[buf]
  if not state or state.path ~= name or state.name ~= vim.api.nvim_buf_get_name(buf) then
    if state then stop(state); if state.timer and not state.timer:is_closing() then state.timer:close() end end
    state = { path = name, name = vim.api.nvim_buf_get_name(buf), expected = stat(name) }
    state.safe = read or state.expected == false
    M.states[buf] = state
  elseif read then state.expected, state.safe, state.error = stat(name), true, nil end
  return state
end
-- Accept a formatter's metadata only after proving that its disk output is
-- exactly the clean buffer. A stale formatter result must never authorize a
-- later autosave to overwrite unrelated external changes.
function M.acknowledge(buf)
  local name = path(buf)
  if not name or vim.bo[buf].modified then return false end
  local encoding = vim.bo[buf].fileencoding
  if encoding ~= '' and encoding ~= 'utf-8' then return false end
  local before, tick = stat(name), vim.api.nvim_buf_get_changedtick(buf)
  if not before or before.size > 5 * 1024 * 1024 then return false end
  local fd = vim.uv.fs_open(name, 'r', 438)
  if not fd then return false end
  local bytes = vim.uv.fs_read(fd, before.size, 0)
  vim.uv.fs_close(fd)
  if not bytes or #bytes ~= before.size then return false end
  local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
  local newline = vim.bo[buf].fileformat == 'dos' and '\r\n' or vim.bo[buf].fileformat == 'mac' and '\r' or '\n'
  local text = table.concat(lines, newline) .. (vim.bo[buf].endofline and newline or '')
  if #lines == 1 and lines[1] == '' then
    local writing = M.writing; M.writing = true
    local ok, empty = pcall(vim.api.nvim_buf_call, buf, function() return vim.fn.wordcount().bytes == 0 end)
    M.writing = writing
    if not ok then return false end
    if empty then text = '' end
  end
  if vim.bo[buf].bomb then text = string.char(239, 187, 191) .. text end
  local after = stat(name)
  if bytes ~= text or not vim.deep_equal(before, after) or vim.bo[buf].modified
    or vim.api.nvim_buf_get_changedtick(buf) ~= tick then return false end
  local state = track(buf, false)
  if not state then return false end
  state.expected, state.safe, state.error = after, true, nil
  return true
end
local function report(state, message)
  if state.error == message then return end
  state.error = message
  local text = ('Autosave paused for ' .. vim.fs.basename(state.path) .. ': ' .. message):gsub('[\r\n]', ' ')
  local width = math.max(20, vim.o.columns - 4)
  while vim.fn.strdisplaywidth(text) > width do text = vim.fn.strcharpart(text, 0, vim.fn.strchars(text) - 1) end
  vim.notify(text,
    vim.log.levels.WARN, { title = 'Jetvim autosave' })
end
local function busy(buf)
  local mode = vim.api.nvim_get_mode()
  return vim.b[buf].jetvim_closing or vim.b[buf].jetvim_hook_running or mode.blocking or mode.mode:match('^[cr]')
    or vim.bo.buftype == 'prompt'
end
local arm
function M.save(buf, reason)
  reason = reason or 'idle'
  if stopped() then return end
  local options = require('jetvim.settings').get().autosave
  if reason == 'idle' and options.debounce == false or reason == 'leave' and options.on_focus_lost == false then return end
  local state = M.states[buf]
  local resolved = path(buf)
  if not state or not resolved or resolved ~= state.path then return end
  if not vim.bo[buf].modified or not vim.bo[buf].modifiable or vim.bo[buf].readonly then return end
  if vim.b[buf].jetvim_closing then return end
  if busy(buf) then arm(buf, 100, reason); return end
  if not state.safe then report(state, 'file was not read; save it explicitly first'); return end
  if not vim.deep_equal(state.expected, stat(state.path)) then
    report(state, 'file changed outside Jetvim; review or reload it before saving'); return
  end
  local confirm = vim.o.confirm
  local previous_error = vim.v.errmsg
  vim.o.confirm = false
  vim.v.errmsg = ''
  -- silent! prevents native write errors from entering a hit-enter prompt.
  -- Check both the error variable and modified flag instead of treating a
  -- suppressed error as a successful save.
  M.writing = true
  local ok, err = pcall(vim.api.nvim_buf_call, buf, function() vim.cmd('silent! keepalt update') end)
  M.writing = false
  local write_error = vim.v.errmsg
  vim.v.errmsg = previous_error
  vim.o.confirm = confirm
  if not ok then report(state, tostring(err)); return end
  if write_error ~= '' or vim.bo[buf].modified then
    report(state, write_error ~= '' and write_error or 'write did not complete'); return
  end
  state.expected, state.safe, state.error = stat(state.path), true, nil
end
arm = function(buf, delay, reason)
  local state = M.states[buf]
  if not state or stopped() then if state then stop(state) end; return end
  if not state.timer then state.timer = vim.uv.new_timer(); state.timer:unref() end
  state.timer:stop()
  state.timer:start(delay, 0, vim.schedule_wrap(function()
    if M.states[buf] == state then M.save(buf, reason) end
  end))
end
function M.schedule(buf)
  buf = buf or vim.api.nvim_get_current_buf()
  if stopped() then stop(M.states[buf]); return end
  if require('jetvim.settings').get().autosave.debounce == false then return end
  if not path(buf) then return end
  local state = track(buf, false)
  if state and vim.bo[buf].modified then arm(buf, require('jetvim.settings').get().autosave.delay_ms) end
end
function M.leave(buf)
  if M.writing or stopped() or require('jetvim.settings').get().autosave.on_focus_lost == false
    or not path(buf) or vim.b[buf].jetvim_closing then return end
  local state = track(buf, false)
  vim.schedule(function()
    if M.states[buf] ~= state or not vim.api.nvim_buf_is_valid(buf) or vim.b[buf].jetvim_closing then return end
    if vim.api.nvim_get_current_buf() == buf then return end
    stop(state)
    M.save(buf, 'leave')
  end)
end
function M.setup()
  M.exiting = false
  local group = vim.api.nvim_create_augroup('JetvimAutosave', { clear = true })
  vim.api.nvim_create_autocmd({ 'BufReadPost', 'BufWritePost' }, { group = group, callback = function(event) track(event.buf, true) end })
  vim.api.nvim_create_autocmd({ 'BufEnter', 'BufNewFile', 'BufFilePost' }, { group = group, callback = function(event) track(event.buf, false) end })
  vim.api.nvim_create_autocmd({ 'TextChanged', 'TextChangedI', 'TextChangedP' }, {
    group = group, callback = function(event) M.schedule(event.buf) end,
  })
  vim.api.nvim_create_autocmd({ 'BufLeave', 'WinLeave' }, { group = group, callback = function(event) M.leave(event.buf) end })
  vim.api.nvim_create_autocmd('User', { group = group, pattern = 'JetvimSettingsChanged', callback = function()
    for buf, state in pairs(M.states) do stop(state); if not stopped() then M.schedule(buf) end end
  end })
  vim.api.nvim_create_autocmd('BufWipeout', { group = group, callback = function(event)
    local state = M.states[event.buf]
    if state then stop(state); if state.timer and not state.timer:is_closing() then state.timer:close() end end
    M.states[event.buf] = nil
  end })
  vim.api.nvim_create_autocmd('VimLeavePre', { group = group, callback = function()
    M.exiting = true
    for _, state in pairs(M.states) do stop(state); if state.timer and not state.timer:is_closing() then state.timer:close() end end
  end })
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do track(buf, false) end
end
return M
