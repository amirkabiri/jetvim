-- Lua settings are layered: installed defaults < user settings < trusted project
-- overrides. Existing project Lua is never evaluated just by opening a project.
local M = { defaults = { autosave = { enabled = true, debounce = true, delay_ms = 1000, on_focus_lost = true }, git = { blame = { enabled = true, mode = 'current_line' } } } }
local function warning(message)
  local text = ('Jetvim settings: ' .. message):gsub('[\r\n]', ' ')
  while vim.fn.strdisplaywidth(text) > math.max(20, vim.o.columns - 4) do
    text = vim.fn.strcharpart(text, 0, vim.fn.strchars(text) - 1)
  end
  vim.notify(text, vim.log.levels.WARN)
end
local function resolve_under(path, root)
  local full = vim.fs.normalize(vim.fn.fnamemodify(path, ':p'))
  local ancestor, parts = full, {}
  while not vim.uv.fs_realpath(ancestor) do
    table.insert(parts, 1, vim.fs.basename(ancestor))
    local parent = vim.fs.dirname(ancestor)
    if not parent or parent == ancestor then return end
    ancestor = parent
  end
  local real = vim.uv.fs_realpath(ancestor)
  for _, part in ipairs(parts) do real = real .. '/' .. part end
  if root == '/' or real == root or real:sub(1, #root + 1) == root .. '/' then return real end
end
local function valid_layer(value)
  if type(value) ~= 'table' then return false end
  if value.autosave ~= nil then
    local autosave = value.autosave
    if type(autosave) ~= 'table' then return false end
    for _, key in ipairs({ 'enabled', 'debounce', 'on_focus_lost' }) do
      if autosave[key] ~= nil and type(autosave[key]) ~= 'boolean' then return false end
    end
    local delay = autosave.delay_ms
    if delay ~= nil and (type(delay) ~= 'number' or delay % 1 ~= 0 or delay < 100 or delay > 60000) then return false end
  end
  if value.hooks ~= nil then
    if type(value.hooks) ~= 'table' then return false end
    if value.hooks.after_save ~= nil and (type(value.hooks.after_save) ~= 'table' or not vim.islist(value.hooks.after_save)) then return false end
  end
  if value.git ~= nil then
    if type(value.git) ~= 'table' then return false end
    if value.git.blame ~= nil then
      local blame = value.git.blame
      if type(blame) ~= 'table' or blame.enabled ~= nil and type(blame.enabled) ~= 'boolean' then return false end
      if blame.mode ~= nil and blame.mode ~= 'current_line' and blame.mode ~= 'all' then return false end
    end
  end
  return true
end
-- Dictionaries inherit sparse keys. Hook lists intentionally replace the whole
-- lower-priority list, including an explicit empty list used to clear hooks.
local function merge(base, override, prefix)
  local result = vim.deepcopy(base)
  for key, value in pairs(override) do
    local replace = prefix == 'hooks' and key == 'after_save'
      or type(value) == 'table' and next(value) ~= nil and vim.islist(value)
    if type(value) == 'table' and type(result[key]) == 'table' and not replace then
      result[key] = merge(result[key], value, prefix == '' and tostring(key) or prefix .. '.' .. tostring(key))
    else result[key] = vim.deepcopy(value) end
  end
  return result
end
local function valid(value)
  return valid_layer(value) and type(value.autosave) == 'table'
    and type(value.autosave.enabled) == 'boolean' and type(value.autosave.delay_ms) == 'number'
end
local function layer(path, optional)
  if not vim.uv.fs_stat(path) and optional then return {} end
  local ok, value = pcall(dofile, path)
  if not ok then return nil, tostring(value) end
  if not valid_layer(value) then return nil, vim.fs.basename(path) .. ': invalid settings value' end
  return value
end
local function emit()
  vim.api.nvim_exec_autocmds('User', { pattern = 'JetvimSettingsChanged', modeline = false })
end
local function project_root() return require('jetvim.project').root end
local function project_path()
  return resolve_under(project_root() .. '/.idea/jetvim/settings.lua', project_root())
end
local function write_new(path, content)
  local fd, reason = vim.uv.fs_open(path, 'wx', 384)
  if not fd then return false, reason end
  local written, err = vim.uv.fs_write(fd, content, 0)
  vim.uv.fs_close(fd)
  if written ~= #content then vim.uv.fs_unlink(path); return false, err or 'Incomplete write' end
  return true
end
local function persist_trust()
  local temporary = M.trust_path .. '.tmp-' .. vim.fn.getpid() .. '-' .. tostring(vim.uv.hrtime())
  local content = vim.json.encode({ version = 1, projects = M.trusted }) .. '\n'
  local ok, reason = write_new(temporary, content)
  if not ok then return false, reason end
  local renamed, err = vim.uv.fs_rename(temporary, M.trust_path)
  if not renamed then vim.uv.fs_unlink(temporary); return false, err end
  return true
end
function M.get() return vim.deepcopy(M.value or M.defaults) end
function M.is_trusted() return M.trusted and M.trusted[project_root()] == true or false end
function M.allow_path(path)
  if not M.home or not M.path then return false end
  local resolved = resolve_under(path, M.home)
  return resolved ~= nil and resolved == M.path
end
function M.reload()
  local defaults, err = layer(M.defaults_path, false)
  if not defaults or not valid(defaults) then warning(err or 'Invalid installed defaults'); return false, err end
  local user
  user, err = layer(M.path, true)
  if not user then warning(err); return false, err end
  local base = merge(defaults, user, '')
  if not valid(base) then warning('Invalid merged user settings'); return false end
  -- Keep a last-good base so revocation can remove project values even when a
  -- subsequently edited global file has become invalid.
  M.defaults, M.base = vim.deepcopy(defaults), vim.deepcopy(base)
  local project = project_path()
  local override = {}
  if project and vim.uv.fs_stat(project) then
    if M.is_trusted() then
      override, err = layer(project, false)
      if not override then warning(err); return false, err end
    elseif not M.notified[project_root()] then
      M.notified[project_root()] = true
      warning('Project Lua skipped. Use :JetvimTrustProject to allow its code.')
    end
  end
  local result = merge(base, override, '')
  if not valid(result) then warning('Invalid merged project settings'); return false end
  M.value = result
  emit()
  return true
end
function M.trust_project()
  M.trusted[project_root()] = true
  local ok, err = persist_trust()
  if not ok then M.trusted[project_root()] = nil; warning('Cannot save project trust: ' .. tostring(err)); return false end
  return M.reload()
end
function M.untrust_project()
  M.trusted[project_root()] = nil
  M.notified[project_root()] = nil
  local ok, err = persist_trust()
  M.value = vim.deepcopy(M.base or M.defaults)
  emit()
  M.reload()
  if not ok then warning('Trust revoked for this session; cannot persist: ' .. tostring(err)) end
  return ok
end
local function open_file(path)
  require('jetvim.tree').editor()
  vim.cmd.edit(vim.fn.fnameescape(path))
  vim.cmd.startinsert()
end
function M.open_user()
  if not vim.uv.fs_stat(M.path) then
    local content = table.concat(vim.fn.readfile(M.defaults_path), '\n') .. '\n'
    local ok, err = write_new(M.path, content)
    if not ok and not vim.uv.fs_stat(M.path) then warning('Cannot create user settings: ' .. tostring(err)); return false end
  end
  open_file(M.path)
  return true
end
function M.open_project()
  local path = project_path()
  if not path then warning('Project settings path leaves the selected project'); return false end
  if not vim.uv.fs_stat(path) then
    if vim.fn.mkdir(vim.fs.dirname(path), 'p') == 0 and not vim.uv.fs_stat(vim.fs.dirname(path)) then
      warning('Cannot create project settings directory'); return false
    end
    local ok, err = write_new(path, '-- Project overrides only; user settings are inherited.\nreturn {}\n')
    if not ok then warning('Cannot create project settings: ' .. tostring(err)); return false end
    -- This exact empty file was intentionally authored through our command.
    -- Existing project files are never granted trust merely by being opened.
    M.trust_project()
  end
  open_file(path)
  return true
end
function M.open()
  vim.ui.select({ 'User settings', 'Project settings' }, { prompt = 'Settings scope' }, function(scope)
    if scope == 'User settings' then M.open_user()
    elseif scope == 'Project settings' then M.open_project() end
  end)
end
function M.setup(root)
  M.defaults_path = root .. '/config/settings.lua'
  local home = vim.env.JETVIM_HOME or root .. '/.jetvim'
  vim.fn.mkdir(home, 'p')
  M.home = assert(vim.uv.fs_realpath(home), 'Cannot resolve Jetvim home')
  M.path = resolve_under(vim.env.JETVIM_SETTINGS_FILE or M.home .. '/settings.lua', M.home)
  if not M.path then error('Jetvim user settings must stay inside JETVIM_HOME') end
  M.trust_path = assert(resolve_under(M.home .. '/trusted-projects.json', M.home), 'Invalid project trust path')
  M.trusted, M.notified = {}, {}
  if vim.uv.fs_stat(M.trust_path) then
    local ok, data = pcall(function() return vim.json.decode(table.concat(vim.fn.readfile(M.trust_path), '\n')) end)
    if ok and type(data) == 'table' and data.version == 1 and type(data.projects) == 'table' then
      for name, trusted in pairs(data.projects) do
        if type(name) == 'string' and name:sub(1, 1) == '/' and trusted == true then M.trusted[name] = true end
      end
    else warning('Invalid project trust metadata; no project is trusted') end
  end
  local defaults = layer(M.defaults_path, false)
  if defaults and valid(defaults) then M.defaults = vim.deepcopy(defaults) end
  M.value, M.base = vim.deepcopy(M.defaults), vim.deepcopy(M.defaults)
  M.reload()
  local group = vim.api.nvim_create_augroup('JetvimSettings', { clear = true })
  vim.api.nvim_create_autocmd('BufWritePost', { group = group, callback = function(event)
    local written = vim.fn.fnamemodify(event.file, ':p')
    if written == M.path or written == project_path() then M.reload() end
  end })
  vim.api.nvim_create_user_command('JetvimSettings', M.open, { desc = 'Choose user or project Lua settings' })
  vim.api.nvim_create_user_command('JetvimUserSettings', M.open_user, { desc = 'Open user Lua settings' })
  vim.api.nvim_create_user_command('JetvimProjectSettings', M.open_project, { desc = 'Open project Lua overrides' })
  vim.api.nvim_create_user_command('JetvimReloadSettings', M.reload, { desc = 'Reload layered Lua settings' })
  vim.api.nvim_create_user_command('JetvimTrustProject', M.trust_project, { desc = 'Allow this project Lua configuration to execute code' })
  vim.api.nvim_create_user_command('JetvimUntrustProject', M.untrust_project, { desc = 'Revoke trust and remove project Lua overrides' })
end
return M
