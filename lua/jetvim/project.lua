local M = {}
function M.setup(root) M.root = vim.uv.fs_realpath(root) end
local function resolve_under(path, root)
  local full = vim.fs.normalize(vim.fn.fnamemodify(path, ':p'))
  local ancestor, tail = full, {}
  while not vim.uv.fs_realpath(ancestor) do
    table.insert(tail, 1, vim.fs.basename(ancestor))
    local parent = vim.fs.dirname(ancestor)
    if parent == ancestor then return nil end
    ancestor = parent
  end
  local real = vim.uv.fs_realpath(ancestor)
  for _, part in ipairs(tail) do real = real .. '/' .. part end
  if root == '/' or real == root or real:sub(1, #root + 1) == root .. '/' then return real end
end
function M.resolve(path) return resolve_under(path, M.root) end
function M.resolve_tool(path) return resolve_under(path, vim.uv.fs_realpath(vim.env.JETVIM_ROOT)) end
function M.open_tool(relative)
  local path = M.resolve_tool(vim.env.JETVIM_ROOT .. '/' .. relative)
  if not path then error('Invalid Jetvim configuration path') end
  require('jetvim.tree').editor()
  vim.cmd.edit(vim.fn.fnameescape(path))
  vim.cmd.startinsert()
end
function M.open(path, line, col)
  local resolved = M.resolve(path)
  if not resolved then
    vim.notify('Jetvim is restricted to ' .. M.root, vim.log.levels.WARN)
    return
  end
  require('jetvim.tree').editor()
  vim.cmd.edit(vim.fn.fnameescape(resolved))
  if line then
    local row = math.min(line, vim.api.nvim_buf_line_count(0))
    local text = vim.api.nvim_buf_get_lines(0, row - 1, row, false)[1] or ''
    vim.api.nvim_win_set_cursor(0, { row, math.min(col or 0, #text) })
  end
  vim.cmd.startinsert()
end
function M.files()
  if vim.fn.executable('rg') == 1 then
    local result = vim.system({ 'rg', '--files', '--hidden', '-g', '!.git', '-g', '!.jetvim', '-g', '!node_modules' },
      { cwd = M.root, text = true }):wait()
    if result.code == 0 or result.code == 1 then
      return vim.split(result.stdout or '', '\n', { trimempty = true })
    end
  end
  local files = {}
  local function walk(dir, prefix)
    local scan = vim.uv.fs_scandir(dir)
    if not scan then return end
    while true do
      local name, kind = vim.uv.fs_scandir_next(scan)
      if not name then break end
      if name ~= '.git' and name ~= '.jetvim' and name ~= 'node_modules' then
        if kind == 'directory' then walk(dir .. '/' .. name, prefix .. name .. '/')
        elseif kind == 'file' then files[#files + 1] = prefix .. name end
      end
    end
  end
  walk(M.root, '')
  table.sort(files)
  return files
end
return M
