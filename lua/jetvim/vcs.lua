-- A project-scoped, asynchronous Git status cache. Rendering only reads this
-- table; it never starts Git or waits for a subprocess.
local M = { _cache = {}, _generation = 0 }
local timer = vim.uv.new_timer()
timer:unref()
local function within(path, root)
  return root == '/' or path == root or path:sub(1, #root + 1) == root .. '/'
end
local function project_root()
  return require('jetvim.project').root
end
local function current(generation, project)
  return generation == M._generation and project == project_root() and vim.env.JETVIM_DISABLE_VCS ~= '1'
end
local function emit()
  vim.api.nvim_exec_autocmds('User', { pattern = 'JetvimVcsChanged', modeline = false })
end
local function publish(cache, project, repo, generation)
  if not current(generation, project) then return end
  M._cache, M._project, M._repo, M._job = cache, project, repo, nil
  emit()
end
local function classify(x, y)
  if x == 'U' or y == 'U' or x .. y == 'AA' or x .. y == 'DD' then return 'conflict' end
  if x == '?' and y == '?' then return 'untracked' end
  if x == '!' and y == '!' then return nil end
  if x == 'D' or y == 'D' then return 'deleted' end
  if x == 'A' or y == 'A' then return 'added' end
  if x ~= ' ' or y ~= ' ' then return 'modified' end
end
function M.parse_status(output, repo, project)
  local fields = vim.split(output, '\0', { plain = true, trimempty = true })
  local result, index = {}, 1
  while index <= #fields do
    local field = fields[index]
    if #field >= 4 and field:sub(3, 3) == ' ' then
      local x, y, relative = field:sub(1, 1), field:sub(2, 2), field:sub(4)
      local path = vim.fs.normalize(repo .. '/' .. relative)
      local status = classify(x, y)
      if status and within(path, project) then result[path] = status end
      -- Porcelain -z gives the destination first, followed by the old path.
      if x == 'R' or y == 'R' or x == 'C' or y == 'C' then index = index + 1 end
    end
    index = index + 1
  end
  return result
end
function M.status(path)
  if vim.env.JETVIM_DISABLE_VCS == '1' or M._project ~= project_root() or type(path) ~= 'string' or path:sub(1, 1) ~= '/' then return nil end
  return M._cache[vim.fs.normalize(path)]
end
local function stop_job()
  local job = M._job
  M._job = nil
  if job and job.kill then pcall(job.kill, job, 15) end
end
local function command(project, args, generation, callback)
  local argv = { 'git', '--no-pager', '--no-optional-locks', '--literal-pathspecs',
    '-c', 'core.fsmonitor=false', '-C', project }
  vim.list_extend(argv, args)
  local ok, job = pcall(vim.system, argv, { text = false, timeout = 10000 }, function(result)
    vim.schedule(function()
      if current(generation, project) then callback(result) end
    end)
  end)
  if ok then M._job = job
  elseif current(generation, project) then publish({}, project, nil, generation) end
end
local function run(project, generation)
  if not current(generation, project) then return end
  if vim.fn.executable('git') ~= 1 then publish({}, project, nil, generation); return end
  command(project, { 'rev-parse', '--show-toplevel' }, generation, function(root)
    if root.code ~= 0 then publish({}, project, nil, generation); return end
    -- Remove exactly Git's delimiter, preserving CR/newline bytes in real paths.
    local repo = (root.stdout or ''):gsub('\n$', '')
    if repo:sub(1, 1) ~= '/' then publish({}, project, nil, generation); return end
    repo = vim.uv.fs_realpath(repo) or vim.fs.normalize(repo)
    command(project, { 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--', '.' }, generation, function(result)
      if result.code ~= 0 then publish({}, project, repo, generation); return end
      publish(M.parse_status(result.stdout or '', repo, project), project, repo, generation)
    end)
  end)
end
function M.refresh()
  local project = project_root()
  M._generation = M._generation + 1
  local generation = M._generation
  timer:stop()
  stop_job()
  if M._project ~= project then
    M._cache, M._project, M._repo = {}, project, nil
    emit()
  end
  if vim.env.JETVIM_DISABLE_VCS == '1' then
    if next(M._cache) then M._cache = {}; emit() end
    return
  end
  timer:start(120, 0, function() vim.schedule(function() run(project, generation) end) end)
end
function M.setup()
  local group = vim.api.nvim_create_augroup('JetvimVcs', { clear = true })
  vim.api.nvim_create_autocmd({ 'BufWritePost', 'FocusGained', 'VimEnter' }, { group = group, callback = M.refresh })
  vim.api.nvim_create_autocmd('VimLeavePre', { group = group, callback = function()
    M._generation = M._generation + 1
    stop_job()
    if not timer:is_closing() then timer:stop(); timer:close() end
  end })
  M.refresh()
end
return M
