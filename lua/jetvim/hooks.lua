-- After-save extensions are argv jobs, never interpolated shell commands.
local M = { states = {}, epoch = 0 }
local function notify(message)
  local text = ('Jetvim hook: ' .. tostring(message)):gsub('[\r\n]', ' ')
  vim.notify(vim.fn.strcharpart(text, 0, math.max(20, vim.o.columns - 4)), vim.log.levels.WARN)
end
local function eligible(buf)
  return vim.api.nvim_buf_is_valid(buf) and vim.api.nvim_buf_is_loaded(buf)
    and vim.bo[buf].buftype == '' and require('jetvim.project').resolve(vim.api.nvim_buf_get_name(buf))
end
local function valid(state)
  return M.states[state.buf] == state and state.epoch == M.epoch and eligible(state.buf)
    and vim.api.nvim_buf_get_name(state.buf) == state.name
end
local function fresh(state)
  return valid(state) and not vim.bo[state.buf].modified
    and vim.api.nvim_buf_get_changedtick(state.buf) == state.tick
end
function M.eslint(output, _, context)
  local decoded = vim.json.decode(output)
  local result = {}
  for _, file in ipairs(decoded) do
    local same = not context or not file.filePath or vim.fs.normalize(file.filePath) == vim.fs.normalize(context.file)
    for _, item in ipairs(file.messages or {}) do
      if same then
        local column = item.column or 1
        if context and context.buffer then
          local line = vim.api.nvim_buf_get_lines(context.buffer, math.max(0, (item.line or 1) - 1), item.line or 1, false)[1] or ''
          local ok, byte = pcall(vim.str_byteindex, line, 'utf-16', column - 1, false)
          if ok then column = byte + 1 end
        end
        result[#result + 1] = { line = item.line or 1, column = column, message = item.message,
          severity = item.severity == 1 and 'warn' or 'error', code = item.ruleId }
      end
    end
  end
  return result
end
local function clear(state)
  if vim.api.nvim_buf_is_valid(state.buf) then vim.b[state.buf].jetvim_hook_running = nil end
  M.states[state.buf] = nil
end
local next_hook, start
local function done(state)
  if not valid(state) then if M.states[state.buf] == state then clear(state) end; return end
  local again = state.pending
  clear(state)
  if again then start(state.buf) end
  local autosave = package.loaded['jetvim.autosave']
  if autosave then autosave.schedule(state.buf) end
end
next_hook = function(state)
  if not valid(state) then if M.states[state.buf] == state then clear(state) end; return end
  state.index = state.index + 1
  local hook = state.hooks[state.index]
  if not hook then done(state); return end
  if not fresh(state) then done(state); return end
  local options
  local name = hook.name or ('save-' .. state.index)
  local source = 'hook:' .. name
  local function finish(result)
    if not valid(state) then if M.states[state.buf] == state then clear(state) end; return end
    state.job = nil
    if not fresh(state) then done(state); return end
    if hook.diagnostics then
      local ok, err = pcall(function()
        local parser = hook.diagnostics == 'eslint' and M.eslint or hook.diagnostics == 'oxlint' and require('jetvim.oxlint').parse or hook.diagnostics
        local entries = parser(result.stdout or '', result, { buffer = state.buf, file = state.path, cwd = options.cwd })
        assert(type(entries) == 'table', 'Diagnostic parser must return a list')
        require('jetvim.api').diagnostics(source, state.buf, entries)
      end)
      if not ok then notify(name .. ': invalid diagnostics: ' .. tostring(err)) end
      if not fresh(state) then done(state); return end
    end
    -- JSON linters return 1 for findings. Other failures are reported.
    if result.code ~= 0 and not ((hook.diagnostics == 'eslint' or hook.diagnostics == 'oxlint') and result.code == 1) then
      notify(name .. ': command failed (exit ' .. tostring(result.code) .. ')')
      next_hook(state); return
    end
    -- External formatters may change disk. Never replace edits typed since save.
    local function reload()
      vim.api.nvim_buf_call(state.buf, function()
        local autoread = vim.bo.autoread
        vim.bo.autoread = true
        local read_ok, err = pcall(vim.cmd, 'silent keepalt checktime')
        vim.bo.autoread = autoread
        if not read_ok then error(err) end
      end)
    end
    local disk = package.loaded['jetvim.disk']
    local ok = pcall(function()
      if disk and disk.with_native_reload then disk.with_native_reload(state.buf, reload) else reload() end
    end)
    if not ok then notify(name .. ': cannot reload formatted file') end
    if ok and valid(state) and not vim.bo[state.buf].modified then
      state.tick = vim.api.nvim_buf_get_changedtick(state.buf)
      local autosave, disk = package.loaded['jetvim.autosave'], package.loaded['jetvim.disk']
      if autosave and autosave.acknowledge(state.buf) and disk and disk.acknowledge then
        disk.acknowledge(state.buf, autosave.states[state.buf].expected)
      end
    end
    next_hook(state)
  end
  if hook.diagnostics then require('jetvim.api').diagnostics(source, state.buf, {}) end
  local argv = {}
  for _, value in ipairs(hook.command) do
    argv[#argv + 1] = value:gsub('{([%w_]+)}', { file = state.path, project = state.root })
  end
  options = { cwd = state.root, text = true, timeout = hook.timeout_ms or 10000 }
  if hook.workspace then
    local success, resolved, err = pcall(require('jetvim.workspace').resolve, state.root, state.path, argv, state.tool_paths, { declared = hook.declared })
    if not success then err, resolved = resolved, nil end
    if not resolved then notify(name .. ': ' .. tostring(err)); next_hook(state); return end
    if resolved.skip then next_hook(state); return end
    argv, options.cwd, options.env = resolved.argv, resolved.cwd, resolved.env
  end
  local ok, job = pcall(vim.system, argv, options, function(result)
    vim.schedule(function() finish(result) end)
  end)
  if ok then state.job = job else notify(name .. ': ' .. tostring(job)); next_hook(state) end
end
start = function(buf)
  local path = eligible(buf)
  if not path or vim.bo[buf].modified then return end
  if M.states[buf] then M.states[buf].pending = true; return end
  local hooks, names = {}, {}
  for _, hook in ipairs((require('jetvim.settings').get().hooks or {}).after_save or {}) do
    local ok, matches = pcall(function()
      assert(type(hook) == 'table' and type(hook.pattern) == 'string' and type(hook.command) == 'table' and vim.islist(hook.command) and #hook.command > 0, 'Expected pattern and command argv')
      assert(hook.declared == nil or type(hook.declared) == 'boolean' and (not hook.declared or hook.workspace == true), 'declared requires workspace=true')
      assert(hook.workspace == nil or type(hook.workspace) == 'boolean', 'workspace must be a boolean')
      assert(hook.name == nil or type(hook.name) == 'string' and hook.name ~= '', 'Hook name must be a nonempty string')
      for _, arg in ipairs(hook.command) do assert(type(arg) == 'string', 'Command arguments must be strings') end
      assert(hook.diagnostics == nil or hook.diagnostics == 'eslint' or hook.diagnostics == 'oxlint' or type(hook.diagnostics) == 'function', 'Unknown diagnostic parser')
      assert(hook.timeout_ms == nil or type(hook.timeout_ms) == 'number' and hook.timeout_ms >= 1 and hook.timeout_ms <= 120000, 'Invalid timeout')
      return vim.regex('\\v' .. hook.pattern):match_str(path) ~= nil
    end)
    if not ok then notify(matches) elseif matches then
      local name = hook.name or ('save-' .. (#hooks + 1))
      if names[name] then notify('Duplicate hook name: ' .. tostring(name))
      else names[name] = true; hooks[#hooks + 1] = hook end
    end
  end
  if #hooks == 0 then return end
  local state = { buf = buf, path = path, name = vim.api.nvim_buf_get_name(buf), root = require('jetvim.project').root, tick = vim.api.nvim_buf_get_changedtick(buf), tool_paths = (require('jetvim.settings').get().hooks or {}).tool_paths or {}, hooks = hooks, index = 0, epoch = M.epoch }
  M.states[buf] = state
  vim.b[buf].jetvim_hook_running = true
  next_hook(state)
end
function M.run(buf) start((buf == nil or buf == 0) and vim.api.nvim_get_current_buf() or buf) end
local function cancel(buf, resume)
  local state = M.states[buf]
  if not state then return end
  if state.job then pcall(state.job.kill, state.job, 15) end
  clear(state)
  local autosave = package.loaded['jetvim.autosave']
  if resume and autosave then vim.schedule(function() autosave.schedule(buf) end) end
end
function M.setup()
  local group = vim.api.nvim_create_augroup('JetvimHooks', { clear = true })
  vim.api.nvim_create_autocmd('BufWritePost', { group = group, callback = function(event) M.run(event.buf) end })
  vim.api.nvim_create_autocmd('BufWipeout', { group = group, callback = function(event) cancel(event.buf) end })
  vim.api.nvim_create_autocmd('BufFilePre', { group = group, callback = function(event) cancel(event.buf, true) end })
  vim.api.nvim_create_autocmd({ 'VimLeavePre', 'User' }, { group = group, pattern = '*', callback = function(event)
    if event.event == 'User' and event.match ~= 'JetvimSettingsChanged' then return end
    M.epoch = M.epoch + 1
    for buf in pairs(M.states) do cancel(buf, event.event == 'User') end
    for source, ns in pairs(require('jetvim.api').namespaces) do
      if source:sub(1, 5) == 'hook:' then vim.diagnostic.reset(ns) end
    end
  end })
end
return M
