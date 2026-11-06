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
-- Inspect script command words without evaluating shell syntax or running a
-- package script. Script arguments/globs never become formatter arguments.
local function segments(script)
  local result, words, word, quote = {}, {}, '', nil
  local function flush() if word ~= '' then words[#words + 1] = word; word = '' end end
  local i = 1
  while i <= #script do
    local char = script:sub(i, i)
    if quote then
      if char == quote then quote = nil else word = word .. char end
    elseif char == '"' or char == "'" then quote = char
    elseif char == '\\' and i < #script then i = i + 1; word = word .. script:sub(i, i)
    elseif char:match('[;&|\n]') then
      flush(); if #words > 0 then result[#result + 1] = words; words = {} end
    elseif char:match('%s') then flush()
    else word = word .. char end
    i = i + 1
  end
  if quote then return nil, 'Unclosed quote in format script' end
  flush(); if #words > 0 then result[#result + 1] = words end
  return result
end
local function script_formatter(package)
  local scripts = type(package.scripts) == 'table' and package.scripts or {}
  local found, active = {}, {}
  local inspect
  inspect = function(name, depth)
    if active[name] or depth > 24 then return nil, 'Cycle or excessive nesting in format script aliases' end
    local script = scripts[name]
    if type(script) ~= 'string' then return nil, 'Missing format script alias: ' .. name end
    active[name] = true
    local commands, err = segments(script)
    if not commands then active[name] = nil; return nil, err end
    for _, words in ipairs(commands) do
      local index = 1
      while words[index] and words[index]:match('^[%w_]+=') do index = index + 1 end
      if words[index] == 'env' or words[index] == 'cross-env' then
        index = index + 1
        while words[index] and words[index]:match('^[%w_]+=') do index = index + 1 end
      end
      local command = words[index] or ''
      if command == 'npx' or command == 'npm' and words[index + 1] == 'exec' then
        index = index + (command == 'npm' and 2 or 1)
        while words[index] and words[index]:sub(1, 1) == '-' do
          local option = words[index]
          index = index + 1
          if option == '--package' or option == '-p' then index = index + 1 end
        end
        command = words[index] or ''
      elseif command == 'pnpm' or command == 'npm' or command == 'yarn' or command == 'bun' then
        local manager = command
        index = index + 1
        while words[index] and words[index]:sub(1, 1) == '-' do
          local option = words[index]
          if option == '-C' or option == '--dir' or option == '--prefix' or option == '--filter' or option == '-F' then
            active[name] = nil; return nil, 'Scoped package-manager format scripts require an explicit formatter'
          end
          index = index + 1
        end
        local sub = words[index]
        if sub == 'exec' then index = index + 1; if words[index] == '--' then index = index + 1 end; command = words[index] or ''
        else
          if sub == 'run' or sub == 'run-script' then index = index + 1 end
          while words[index] and words[index]:sub(1, 1) == '-' do index = index + 1 end
          local alias = words[index]
          if alias and type(scripts[alias]) == 'string' then
            local ok; ok, err = inspect(alias, depth + 1)
            if not ok then active[name] = nil; return nil, err end
            command = ''
          elseif manager ~= 'npm' then command = alias or ''
          else command = '' end
        end
      end
      local tool = vim.fs.basename(command):gsub('@.*$', '')
      if tool == 'oxfmt' or tool == 'prettier' then found[tool] = true end
    end
    active[name] = nil
    return true
  end
  for _, name in ipairs({ 'format', 'lint:format' }) do
    if type(scripts[name]) == 'string' then
      local ok, err = inspect(name, 0)
      if not ok then return nil, err end
    end
  end
  if found.oxfmt and found.prettier then return nil, 'Ambiguous project formatter: scripts declare both Oxfmt and Prettier' end
  return found.oxfmt and 'oxfmt' or found.prettier and 'prettier' or nil
end
local prettier_configs = {
  '.prettierrc', '.prettierrc.json', '.prettierrc.json5', '.prettierrc.yaml', '.prettierrc.yml', '.prettierrc.toml',
  '.prettierrc.js', '.prettierrc.cjs', '.prettierrc.mjs', '.prettierrc.ts', '.prettierrc.cts', '.prettierrc.mts',
  'prettier.config.js', 'prettier.config.cjs', 'prettier.config.mjs', 'prettier.config.ts', 'prettier.config.cts', 'prettier.config.mts',
}
local function formatter(dirs)
  local packages, closest = {}, nil
  for _, dir in ipairs(dirs) do
    local package = json(dir .. '/package.json')
    if package then packages[dir] = package; closest = closest or dir end
  end
  if closest then
    local chosen, err = script_formatter(packages[closest])
    if chosen or err then return chosen, err end
  end
  for _, dir in ipairs(dirs) do
    local oxfmt = file(dir .. '/.oxfmtrc.json') or file(dir .. '/.oxfmtrc.jsonc')
    local prettier = packages[dir] and packages[dir].prettier ~= nil and packages[dir].prettier ~= false
    for _, name in ipairs(prettier_configs) do if file(dir .. '/' .. name) then prettier = true; break end end
    if oxfmt and prettier then return nil, 'Ambiguous project formatter: both Oxfmt and Prettier configurations exist' end
    if oxfmt or prettier then return oxfmt and 'oxfmt' or 'prettier' end
  end
  for _, dir in ipairs(dirs) do
    if packages[dir] and dir ~= closest then
      local chosen, err = script_formatter(packages[dir])
      if chosen or err then return chosen, err end
    end
  end
  return nil, 'No project formatter declared; configure Prettier or Oxfmt first'
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
  local selected_formatter
  if command == 'project-formatter' then
    local err
    selected_formatter, err = formatter(dirs)
    if not selected_formatter then return nil, err end
    argv = vim.deepcopy(argv)
    command, argv[1] = selected_formatter, selected_formatter
  end
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
  local result = { argv = vim.deepcopy(argv), cwd = cwd, env = {}, formatter = selected_formatter }
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
