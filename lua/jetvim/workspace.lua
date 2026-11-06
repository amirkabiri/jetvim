-- Resolve already-installed workspace tools. No package managers or downloads.
local M = {}
local function inside(path, root)
  return root == '/' or path == root or path:sub(1, #root + 1) == root .. '/'
end
local function file(path)
  local stat = vim.uv.fs_stat(path)
  return stat and stat.type == 'file'
end
local function json(path)
  local ok, value = pcall(function() return vim.json.decode(table.concat(vim.fn.readfile(path), '\n')) end)
  return ok and type(value) == 'table' and value or nil
end
local function directories(root, path)
  local result, dir = {}, vim.fs.dirname(path)
  while dir and inside(dir, root) do
    result[#result + 1] = dir
    if dir == root then break end
    local parent = vim.fs.dirname(dir)
    if parent == dir then break end
    dir = parent
  end
  return result
end
local function executable(path, root)
  local resolved = vim.uv.fs_realpath(path)
  return resolved and inside(resolved, root) and file(resolved) and vim.fn.executable(path) == 1
end
local function explicit_config(argv)
  for index = 2, #argv do
    local arg = argv[index]
    if arg == '--' then break end
    if arg == '--config' or arg == '-c' then return argv[index + 1], true end
    local value = arg:match('^%-%-config=(.*)$') or arg:match('^%-c(.+)$')
    if value then return value, true end
  end
end
local function config_mode(path)
  local name = vim.fs.basename(path)
  if name:match('^%.eslintrc') or name:match('%.json$') or name:match('%.ya?ml$') then return 'false' end
  return 'true'
end
function M.resolve(root, path, argv, tool_paths)
  root = vim.uv.fs_realpath(root)
  if not root then return nil, 'Workspace root does not exist' end
  path = vim.uv.fs_realpath(path) or vim.fs.normalize(path)
  if not inside(path, root) then return nil, 'Saved file is outside the workspace' end
  local dirs, cwd = directories(root, path), root
  for _, dir in ipairs(dirs) do if file(dir .. '/package.json') then cwd = dir; break end end
  local command = argv[1]
  if type(command) ~= 'string' or command == '' then return nil, 'Workspace command is missing' end
  local selected
  if command:find('/', 1, true) then
    local candidate = command:sub(1, 1) == '/' and command or vim.fs.normalize(cwd .. '/' .. command)
    if executable(candidate, root) then selected = candidate end
  else
    for _, dir in ipairs(dirs) do
      local candidate = dir .. '/node_modules/.bin/' .. command
      if executable(candidate, root) then selected = candidate; break end
    end
    if not selected then
      for _, dir in ipairs(tool_paths or {}) do
        if type(dir) ~= 'string' or dir == '' or dir:sub(1, 1) == '/' then return nil, 'tool_paths must contain project-relative directories' end
        local candidate = vim.fs.normalize(root .. '/' .. dir .. '/' .. command)
        if not inside(candidate, root) then return nil, 'Tool path leaves the workspace' end
        if executable(candidate, root) then selected = candidate; break end
      end
    end
  end
  local function ready(result)
    if not selected then return nil, 'Workspace tool is not installed: ' .. command end
    result.argv[1] = selected
    return result
  end
  local function add_config(result, candidate)
    local index = #result.argv + 1
    for i, arg in ipairs(result.argv) do if arg == '--' then index = i; break end end
    table.insert(result.argv, index, '--config')
    table.insert(result.argv, index + 1, candidate)
  end
  local result = { argv = vim.deepcopy(argv), cwd = cwd, env = {} }
  if vim.fs.basename(command) ~= 'eslint' then return ready(result) end
  local explicit, supplied = explicit_config(argv)
  if supplied then
    -- Preserve argv exactly. ESLint itself reports missing/invalid CLI values.
    if explicit then result.env.ESLINT_USE_FLAT_CONFIG = config_mode(explicit) end
    result.config = explicit
    return ready(result)
  end
  for _, dir in ipairs(dirs) do
    for _, name in ipairs({ 'eslint.config.js', 'eslint.config.mjs', 'eslint.config.cjs' }) do
      local candidate = dir .. '/' .. name
      if file(candidate) then
        add_config(result, candidate)
        result.config, result.env.ESLINT_USE_FLAT_CONFIG = candidate, 'true'
        return ready(result)
      end
    end
    for _, name in ipairs({ '.eslintrc.js', '.eslintrc.cjs', '.eslintrc.json', '.eslintrc.yaml', '.eslintrc.yml', '.eslintrc' }) do
      local candidate = dir .. '/' .. name
      if file(candidate) then
        add_config(result, candidate)
        result.config, result.env.ESLINT_USE_FLAT_CONFIG = candidate, 'false'
        return ready(result)
      end
    end
    local package = json(dir .. '/package.json')
    if package and type(package.eslintConfig) == 'table' then
      result.config, result.env.ESLINT_USE_FLAT_CONFIG = dir .. '/package.json', 'false'
      return ready(result)
    end
  end
  result.skip = true
  return result
end
M.contains = inside
return M
