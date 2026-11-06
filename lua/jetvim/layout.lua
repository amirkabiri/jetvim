-- Project layout is data, never executable project configuration. Desired sizes
-- are separate from host-terminal clamps and temporary split rearrangements.
local M = { desired = {}, tracked = {}, dirty = false }
local axes = { tree_width = 'width', git_height = 'height', git_list_width = 'width', terminal_height = 'height' }
local function size(entry)
  if not vim.api.nvim_win_is_valid(entry.win) or vim.api.nvim_win_get_buf(entry.win) ~= entry.buf then return end
  return entry.axis == 'width' and vim.api.nvim_win_get_width(entry.win) or vim.api.nvim_win_get_height(entry.win)
end
local function topology()
  local ids = {}
  for _, win in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
    if vim.api.nvim_win_get_config(win).relative == '' then ids[#ids + 1] = win end
  end
  table.sort(ids)
  return table.concat(ids, ','), vim.o.columns .. ':' .. vim.o.lines
end
local function baseline()
  M.topology, M.host = topology()
  for _, entry in pairs(M.tracked) do entry.actual = size(entry) end
end
local function path()
  local project = require('jetvim.project')
  return project.resolve(project.root .. '/.idea/jetvim/layout.json')
end
local function ensure_loaded()
  local root = require('jetvim.project').root
  if M.root == root then return end
  M.root, M.desired, M.tracked, M.dirty = root, {}, {}, false
  local file = path()
  if file and vim.uv.fs_stat(file) then
    local ok, data = pcall(function() return vim.json.decode(table.concat(vim.fn.readfile(file), '\n')) end)
    if ok and type(data) == 'table' and data.version == 1 and type(data.sizes) == 'table' then
      for key, value in pairs(data.sizes) do
        if axes[key] and type(value) == 'number' and value % 1 == 0 and value >= 1 and value <= 10000 then M.desired[key] = value end
      end
    end
  end
  if not M.setup_done then
    M.setup_done = true
    local group = vim.api.nvim_create_augroup('JetvimLayout', { clear = true })
    vim.api.nvim_create_autocmd('WinResized', { group = group, callback = function() M.capture() end })
    -- Focusing an undersized editor can apply Vim's preferred winwidth/height
    -- without changing split topology. That automatic expansion is not a user
    -- resize of its neighboring tool pane.
    vim.api.nvim_create_autocmd({ 'VimResized', 'WinEnter' }, { group = group, callback = baseline })
    vim.api.nvim_create_autocmd('VimLeavePre', { group = group, callback = function() M.capture(); M.flush() end })
  end
end
function M.get(key, fallback)
  ensure_loaded()
  return M.desired[key] or fallback
end
function M.flush()
  if not M.dirty then return end
  local file = path()
  if not file then return end
  local directory = vim.fs.dirname(file)
  local ok = pcall(vim.fn.mkdir, directory, 'p')
  if not ok or not path() or not vim.uv.fs_stat(directory) then return end
  local temporary = file .. '.tmp-' .. vim.fn.getpid() .. '-' .. tostring(vim.uv.hrtime())
  if not require('jetvim.project').resolve(temporary) then return end
  local fd = vim.uv.fs_open(temporary, 'wx', 384)
  if not fd then return end
  local content = vim.json.encode({ version = 1, sizes = M.desired }) .. '\n'
  local written = vim.uv.fs_write(fd, content, 0)
  vim.uv.fs_close(fd)
  if written ~= #content or not path() or not vim.uv.fs_rename(temporary, file) then vim.uv.fs_unlink(temporary); return end
  M.dirty = false
end
function M.capture(key)
  ensure_loaded()
  if M.mutating then return end
  local topology_now, host = topology()
  if topology_now ~= M.topology or host ~= M.host then baseline(); return end
  local changed = false
  for name, entry in pairs(M.tracked) do
    local actual = size(entry)
    if (not key or key == name) and actual and entry.actual and actual ~= entry.actual then
      M.desired[name], M.dirty, changed = actual, true, true
    end
  end
  baseline()
  if changed then
    M.serial = (M.serial or 0) + 1
    local serial = M.serial
    vim.defer_fn(function() if M.serial == serial then M.flush() end end, 80)
  end
end
function M.begin()
  M.capture()
  local token = {}
  M.mutations = M.mutations or {}
  M.mutations[#M.mutations + 1] = token
  M.mutating = true
  -- Recover if a split command fails before its caller can finish restoration.
  vim.schedule(function()
    local found = false
    for index, pending in ipairs(M.mutations) do
      if pending == token then table.remove(M.mutations, index); found = true; break end
    end
    if not found then return end
    M.mutating = #M.mutations > 0
    if not M.mutating then baseline() end
  end)
end
function M.finish()
  if M.mutations then table.remove(M.mutations) end
  M.mutating = M.mutations and #M.mutations > 0
  baseline()
end
function M.rebase() baseline() end
function M.attach(key, win)
  ensure_loaded()
  assert(axes[key], 'Unknown pane dimension')
  M.tracked[key] = { win = win, axis = axes[key], buf = vim.api.nvim_win_get_buf(win) }
  baseline()
end
function M.detach(key)
  M.tracked[key] = nil
  baseline()
end
return M
