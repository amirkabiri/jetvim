-- Git change bars live in the left sign column. Baselines are read from HEAD;
-- ordinary typing only diffs the cached text and never starts a Git process.
local M = { states = {}, namespace = vim.api.nvim_create_namespace('JetvimGitGutter'), max_bytes = 5 * 1024 * 1024 }
local signs = {
  added = { text = '▎', group = 'JetvimGutterAdded', priority = 7 },
  modified = { text = '▎', group = 'JetvimGutterModified', priority = 7 },
  deleted = { text = '▸', group = 'JetvimGutterDeleted', priority = 8 },
}
local function disabled() return vim.env.JETVIM_DISABLE_VCS == '1' end
local function eligible(buf)
  return vim.api.nvim_buf_is_valid(buf) and vim.api.nvim_buf_is_loaded(buf)
    and vim.bo[buf].buftype == '' and vim.api.nvim_buf_get_name(buf) ~= ''
end
local function cancel(state)
  if state.job and state.job.kill then pcall(state.job.kill, state.job, 15) end
  state.job = nil
end
local function clear(buf)
  if vim.api.nvim_buf_is_valid(buf) then vim.api.nvim_buf_clear_namespace(buf, M.namespace, 0, -1) end
end
local function finish(buf, state, baseline)
  state.baseline, state.pending = baseline, false
  if baseline ~= nil then M.render(buf) else clear(buf) end
end
local function current(buf, state, generation)
  return not disabled() and eligible(buf) and M.states[buf] == state and state.generation == generation
    and vim.api.nvim_buf_get_name(buf) == state.path and require('jetvim.project').root == state.project
end
local function snapshot(buf)
  local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
  if #lines == 1 and lines[1] == '' then
    -- An empty file and one real blank line share the same API line array.
    -- wordcount preserves Vim's internal empty-buffer distinction.
    local bytes = vim.api.nvim_buf_call(buf, function() return vim.fn.wordcount().bytes end)
    if bytes == 0 then return '' end
  end
  local newline = vim.bo[buf].fileformat == 'dos' and '\r\n' or '\n'
  return table.concat(lines, newline) .. (vim.bo[buf].endofline and newline or '')
end
function M.compute(base, text, line_count)
  if #base > M.max_bytes or #text > M.max_bytes or base:find('\0', 1, true) or text:find('\0', 1, true) then return {} end
  local hunks = vim.diff(base, text, { result_type = 'indices', algorithm = 'histogram' })
  local marks = {}
  local function add(row, kind)
    marks[#marks + 1] = { row = math.max(1, math.min(line_count, row)), kind = kind }
  end
  for _, hunk in ipairs(hunks) do
    local old_count, start, new_count = hunk[2], hunk[3], hunk[4]
    if old_count == 0 then
      for row = start, start + new_count - 1 do add(row, 'added') end
    elseif new_count == 0 then add(start, 'deleted')
    else
      for row = start, start + new_count - 1 do
        add(row, row - start < old_count and 'modified' or 'added')
      end
      if old_count > new_count then add(start + new_count, 'deleted') end
    end
  end
  return marks
end
function M.render(buf)
  if not buf or buf == 0 then buf = vim.api.nvim_get_current_buf() end
  local state = M.states[buf]
  if not eligible(buf) or not state or state.baseline == nil or disabled() then clear(buf); return end
  if state.path ~= vim.api.nvim_buf_get_name(buf) or state.project ~= require('jetvim.project').root then clear(buf); return end
  local text = snapshot(buf)
  local encoding = vim.bo[buf].fileencoding
  local base = state.baseline
  if encoding ~= '' and encoding ~= 'utf-8' then base = vim.iconv(base, encoding, 'utf-8') end
  if base:sub(1, 3) == string.char(239, 187, 191) then base = base:sub(4) end
  clear(buf)
  local ok, marks = pcall(M.compute, base, text, vim.api.nvim_buf_line_count(buf))
  if not ok then return end
  for _, mark in ipairs(marks) do
    local sign = signs[mark.kind]
    vim.api.nvim_buf_set_extmark(buf, M.namespace, mark.row - 1, 0, {
      sign_text = sign.text, sign_hl_group = sign.group, priority = sign.priority,
    })
  end
end
local function binary_file(path)
  local stat = vim.uv.fs_stat(path)
  if not stat or stat.type ~= 'file' then return false end
  local fd = vim.uv.fs_open(path, 'r', 438)
  if not fd then return false end
  local value = vim.uv.fs_read(fd, 8192, 0)
  vim.uv.fs_close(fd)
  return value and value:find('\0', 1, true) ~= nil
end
local function command(buf, state, generation, cwd, args, callback)
  local argv = { 'git', '--no-pager', '--no-optional-locks' }
  -- check-ignore parses literal pathname arguments and rejects literal magic
  -- injected by --literal-pathspecs. The ./ prefix below protects names that
  -- themselves begin with ':', without turning them into pathspec syntax.
  if args[1] ~= 'check-ignore' then argv[#argv + 1] = '--literal-pathspecs' end
  vim.list_extend(argv, { '-c', 'core.fsmonitor=false', '-C', cwd })
  vim.list_extend(argv, args)
  local ok, job = pcall(vim.system, argv, { text = false, timeout = 10000 }, function(result)
    vim.schedule(function()
      if current(buf, state, generation) then state.job = nil; callback(result) end
    end)
  end)
  if ok then state.job = job else finish(buf, state, nil) end
end
local function fetch(buf, state, generation)
  if not current(buf, state, generation) then return end
  if vim.fn.executable('git') ~= 1 then finish(buf, state, nil); return end
  command(buf, state, generation, state.project, { 'rev-parse', '--show-toplevel' }, function(root)
    if root.code ~= 0 then finish(buf, state, nil); return end
    local repo = (root.stdout or ''):gsub('\n$', '')
    repo = vim.uv.fs_realpath(repo)
    if not repo or state.path:sub(1, #repo + 1) ~= repo .. '/' then finish(buf, state, nil); return end
    local relative = state.path:sub(#repo + 2)
    command(buf, state, generation, repo, { 'check-ignore', '-q', '--', './' .. relative }, function(ignored)
      if ignored.code == 0 then finish(buf, state, nil); return end
      if ignored.code ~= 1 then finish(buf, state, nil); return end
      command(buf, state, generation, repo, { 'cat-file', 'blob', 'HEAD:' .. relative }, function(blob)
        if blob.code ~= 0 and blob.code ~= 128 then finish(buf, state, nil); return end
        if binary_file(state.path) then finish(buf, state, nil); return end
        finish(buf, state, blob.code == 0 and (blob.stdout or '') or '')
      end)
    end)
  end)
end
function M.refresh(buf)
  if not buf or buf == 0 then buf = vim.api.nvim_get_current_buf() end
  if disabled() or not eligible(buf) then clear(buf); return end
  local project = require('jetvim.project').root
  local path = require('jetvim.project').resolve(vim.api.nvim_buf_get_name(buf))
  if not path then clear(buf); return end
  local stat = vim.uv.fs_stat(path)
  if stat and stat.size > M.max_bytes then clear(buf); return end
  local state = M.states[buf]
  if not state then state = { generation = 0 }; M.states[buf] = state end
  if state.path ~= path or state.project ~= project then state.baseline = nil; clear(buf) end
  cancel(state)
  state.generation = state.generation + 1
  state.path, state.project, state.pending = path, project, true
  local generation = state.generation
  vim.defer_fn(function() fetch(buf, state, generation) end, 120)
end
function M.changed(buf)
  if not buf or buf == 0 then buf = vim.api.nvim_get_current_buf() end
  if disabled() or not eligible(buf) then clear(buf); return end
  local state = M.states[buf]
  if not state or state.path ~= vim.api.nvim_buf_get_name(buf) then M.refresh(buf); return end
  state.render_generation = (state.render_generation or 0) + 1
  local generation = state.render_generation
  vim.defer_fn(function()
    if M.states[buf] == state and state.render_generation == generation then M.render(buf) end
  end, 80)
end
function M.setup()
  local group = vim.api.nvim_create_augroup('JetvimGitGutter', { clear = true })
  vim.api.nvim_create_autocmd({ 'BufReadPost', 'BufNewFile', 'BufFilePost', 'BufWritePost', 'BufEnter', 'FocusGained' }, {
    group = group, callback = function(event) M.refresh(event.buf) end,
  })
  vim.api.nvim_create_autocmd({ 'TextChanged', 'TextChangedI', 'TextChangedP' }, {
    group = group, callback = function(event) M.changed(event.buf) end,
  })
  vim.api.nvim_create_autocmd('User', { group = group, pattern = 'JetvimVcsChanged', callback = function()
    for _, buf in ipairs(vim.api.nvim_list_bufs()) do if eligible(buf) then M.refresh(buf) end end
  end })
  vim.api.nvim_create_autocmd('BufWipeout', { group = group, callback = function(event)
    local state = M.states[event.buf]
    if state then state.generation = state.generation + 1; cancel(state) end
    M.states[event.buf] = nil
  end })
  vim.api.nvim_create_autocmd('VimLeavePre', { group = group, callback = function()
    for _, state in pairs(M.states) do state.generation = state.generation + 1; cancel(state) end
  end })
  M.refresh()
end
return M
