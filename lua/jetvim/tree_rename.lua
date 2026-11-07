-- Same-parent filesystem renames preserve native buffer state and dirty edits.
local M = {}
local function within(path, root)
  return root == '/' or path == root or path:sub(1, #root + 1) == root .. '/'
end
local function valid_path(path, root)
  return type(path) == 'string' and path:sub(1, 1) == '/' and vim.fs.normalize(path) == path
    and path ~= root and within(path, root) and vim.uv.fs_realpath(root) == root
    and vim.uv.fs_realpath(vim.fs.dirname(path)) == vim.fs.dirname(path)
end
local function same(a, b)
  return a and b and a.type == b.type and a.dev == b.dev and a.ino == b.ino
end
local function case_alias(source, destination, expected)
  local first, second = vim.fs.basename(source), vim.fs.basename(destination)
  if first == second or vim.fn.tolower(first) ~= vim.fn.tolower(second)
    or vim.fs.dirname(source) ~= vim.fs.dirname(destination)
    or not same(expected, vim.uv.fs_lstat(destination)) then return false end
  local scan = vim.uv.fs_scandir(vim.fs.dirname(source))
  if not scan then return false end
  local old, new = false, false
  while true do
    local name = vim.uv.fs_scandir_next(scan)
    if not name then break end
    if name == first then old = true elseif name == second then new = true end
  end
  return old and not new
end
local function version(path)
  local stat = vim.uv.fs_stat(path)
  if not stat or stat.type ~= 'file' then return false end
  return { dev = stat.dev, ino = stat.ino, size = stat.size, mtime = stat.mtime }
end
local function check_versions(values)
  for _, buf in ipairs(values) do
    if vim.api.nvim_buf_is_loaded(buf) then
      for _, module in ipairs({ 'jetvim.autosave', 'jetvim.disk' }) do
        local provider = package.loaded[module]
        local state = provider and provider.states[buf]
        if state and not vim.deep_equal(state.expected, version(vim.api.nvim_buf_get_name(buf))) then
          error('File changed outside Jetvim; review or reload it before renaming')
        end
      end
    end
  end
end
local function buffers(path, directory)
  local result = {}
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    local name = vim.api.nvim_buf_get_name(buf)
    if name == path or directory and within(name, path) then result[#result + 1] = buf end
  end
  return result
end
local function check_hooks(values)
  local hooks = package.loaded['jetvim.hooks']
  for _, buf in ipairs(values) do
    if vim.b[buf].jetvim_hook_running or hooks and hooks.states[buf] then
      error('Wait for the file save hook to finish before renaming')
    end
  end
end
local function save_undo(item)
  local buf = item.buf
  if vim.api.nvim_buf_call(buf, function() return vim.fn.undotree().seq_last end) == 0 then return end
  local home = vim.env.JETVIM_HOME or vim.env.JETVIM_ROOT .. '/.jetvim'
  vim.fn.mkdir(home .. '/tmp', 'p')
  if not item.undo then
    local fd, path = vim.uv.fs_mkstemp(home .. '/tmp/rename-XXXXXX')
    if not fd then error('Cannot preserve undo history: ' .. tostring(path)) end
    vim.uv.fs_close(fd)
    item.undo = path
  end
  local path = item.undo
  local ok, err = pcall(vim.api.nvim_buf_call, buf, function() vim.cmd('silent wundo! ' .. vim.fn.fnameescape(path)) end)
  if not ok then vim.uv.fs_unlink(path); error(err) end
end
local function snapshot(buf, destination)
  local item = { buf = buf, old = vim.api.nvim_buf_get_name(buf), new = destination,
    loaded = vim.api.nvim_buf_is_loaded(buf), views = {}, clients = {} }
  local autosave, disk = package.loaded['jetvim.autosave'], package.loaded['jetvim.disk']
  item.autosave, item.disk = autosave and autosave.states[buf], disk and disk.states[buf]
  if not item.loaded then return item end
  item.lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
  item.empty = vim.api.nvim_buf_call(buf, function() return vim.fn.wordcount().bytes == 0 end)
  item.options = {}
  for _, name in ipairs({ 'modified', 'readonly', 'modifiable', 'fileformat', 'fileencoding', 'bomb', 'endofline', 'fixendofline', 'filetype' }) do
    item.options[name] = vim.bo[buf][name]
  end
  for _, win in ipairs(vim.fn.win_findbuf(buf)) do
    item.views[win] = vim.api.nvim_win_call(win, vim.fn.winsaveview)
  end
  for _, client in ipairs(vim.lsp.get_clients({ bufnr = buf, _uninitialized = true })) do item.clients[#item.clients + 1] = client.id end
  save_undo(item)
  return item
end
local function detach(item)
  for _, id in ipairs(item.clients) do
    if vim.lsp.buf_is_attached(item.buf, id) then vim.lsp.buf_detach_client(item.buf, id) end
  end
end
local function reattach(item)
  if not vim.api.nvim_buf_is_valid(item.buf) then return end
  for _, id in ipairs(item.clients) do
    local client = vim.lsp.get_client_by_id(id)
    local filetypes = client and client.config.filetypes
    local root = client and client.config.root_dir
    local name = vim.api.nvim_buf_get_name(item.buf)
    local workspace = not root or type(root) == 'string' and vim.uv.fs_realpath(root) == root and within(name, root)
    if client and client.workspace_folders and #client.workspace_folders > 0 then
      workspace = false
      for _, folder in ipairs(client.workspace_folders) do
        local valid, path = pcall(vim.uri_to_fname, folder.uri)
        if valid and vim.uv.fs_realpath(path) == path and within(name, path) then workspace = true; break end
      end
    end
    if client and workspace and not client:is_stopped() and (not filetypes or vim.tbl_contains(filetypes, vim.bo[item.buf].filetype)) then
      vim.lsp.buf_attach_client(item.buf, id)
    end
  end
end
local function restore(item, name, reload)
  local buf = item.buf
  if not vim.api.nvim_buf_is_valid(buf) then error('An open buffer was removed during renaming') end
  if vim.api.nvim_buf_get_name(buf) ~= name then vim.api.nvim_buf_set_name(buf, name) end
  if item.loaded then
    vim.api.nvim_buf_call(buf, function()
      local read, read_error = true, nil
      if reload then
        vim.bo.readonly, vim.bo.modifiable = false, true
        local previous_error = vim.v.errmsg
        vim.v.errmsg = ''
        read, read_error = pcall(vim.cmd, 'silent! keepalt edit!')
        local native_error = vim.v.errmsg
        vim.v.errmsg = previous_error
        if read and native_error ~= '' then read, read_error = false, native_error end
      end
      local filetype = name == item.old and item.options.filetype or vim.filetype.match({ filename = name, buf = buf }) or ''
      if vim.bo.filetype ~= filetype then vim.bo.filetype = filetype end
      vim.bo.modifiable = true
      if item.empty then vim.api.nvim_buf_set_lines(buf, 0, -1, false, {})
      elseif not vim.deep_equal(vim.api.nvim_buf_get_lines(buf, 0, -1, false), item.lines) or vim.fn.wordcount().bytes == 0 then
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, item.lines)
      end
      for option, value in pairs(item.options) do if option ~= 'filetype' and option ~= 'modifiable' then vim.bo[option] = value end end
      if item.undo then vim.cmd('silent rundo ' .. vim.fn.fnameescape(item.undo)) end
      vim.bo.modifiable = item.options.modifiable
      if not read then error(read_error) end
    end)
    for win, view in pairs(item.views) do
      if vim.api.nvim_win_is_valid(win) and vim.api.nvim_win_get_buf(win) == buf then vim.api.nvim_win_call(win, function() vim.fn.winrestview(view) end) end
    end
  end
  local autosave, disk = package.loaded['jetvim.autosave'], package.loaded['jetvim.disk']
  if autosave then autosave.rebind(buf, item.autosave) end
  if disk then disk.rebind(buf, item.disk) end
end
function M.run(tree)
  if tree.renaming or not tree.is_tree_window(vim.api.nvim_get_current_win()) then return end
  local origin = vim.api.nvim_get_current_win()
  local entry = tree.rows[vim.api.nvim_win_get_cursor(origin)[1]]
  if not entry or entry.root then return end
  local project = require('jetvim.project')
  local root, source = project.root, entry.path
  if not valid_path(source, root) then vim.notify('Path must stay inside the project', vim.log.levels.WARN); return end
  local initial = vim.uv.fs_lstat(source)
  if not initial then vim.notify('File is no longer available', vim.log.levels.WARN); return end
  local directory, held = initial.type == 'directory', {}
  local function hold(values)
    check_hooks(values)
    check_versions(values)
    for _, buf in ipairs(values) do
      if not held[buf] then held[buf] = { closing = vim.b[buf].jetvim_closing }; vim.b[buf].jetvim_closing = true end
    end
  end
  local function release()
    tree.renaming = false
    for buf, previous in pairs(held) do
      if vim.api.nvim_buf_is_valid(buf) and not previous.failed then
        vim.b[buf].jetvim_closing = previous.closing
        local autosave = package.loaded['jetvim.autosave']
        if autosave then pcall(autosave.schedule, buf) end
      end
    end
    tree.renaming = false
  end
  local ok, err = pcall(hold, buffers(source, directory))
  if not ok then release(); vim.notify('Cannot rename: ' .. tostring(err), vim.log.levels.WARN); return end
  tree.renaming = true
  local function accept(name)
    local items, moved, destination = {}, false, nil
    local autosave, disk = package.loaded['jetvim.autosave'], package.loaded['jetvim.disk']
    local writing, reloading = autosave and autosave.writing, disk and disk.reloading
    if autosave then autosave.writing = true end
    if disk then disk.reloading = true end
    local success, failure = pcall(function()
      if name == nil or name == vim.fs.basename(source) then return end
      if name == '' or name == '.' or name == '..' or name:find('[/%z\r\n]') or name:find('\\', 1, true) then error('Enter a file or folder name without a path') end
      destination = vim.fs.dirname(source) .. '/' .. name
      if project.root ~= root or not valid_path(source, root) or not valid_path(destination, root) then error('Project or parent path changed; rename cancelled') end
      local current = vim.uv.fs_lstat(source)
      if not same(initial, current) then error('File changed; rename cancelled') end
      if vim.uv.fs_lstat(destination) and not case_alias(source, destination, initial) then error('A file or folder already exists with that name') end
      local values = buffers(source, directory)
      hold(values)
      local owners = {}
      for _, buf in ipairs(values) do owners[buf] = true end
      for _, buf in ipairs(vim.api.nvim_list_bufs()) do
        local name = vim.api.nvim_buf_get_name(buf)
        if not owners[buf] and (name == destination or directory and within(name, destination)) then error('Another buffer already uses that name') end
      end
      for _, buf in ipairs(values) do
        local old = vim.api.nvim_buf_get_name(buf)
        local target = destination .. old:sub(#source + 1)
        for _, other in ipairs(vim.api.nvim_list_bufs()) do
          if not owners[other] and vim.api.nvim_buf_get_name(other) == target then error('Another buffer already uses that name') end
        end
        items[#items + 1] = snapshot(buf, target)
      end
      for _, item in ipairs(items) do
        detach(item); vim.api.nvim_buf_set_name(item.buf, item.new)
        if item.loaded and not vim.deep_equal(vim.api.nvim_buf_get_lines(item.buf, 0, -1, false), item.lines) then
          item.lines = vim.api.nvim_buf_get_lines(item.buf, 0, -1, false)
          item.options.modified = vim.bo[item.buf].modified
          item.empty = vim.api.nvim_buf_call(item.buf, function() return vim.fn.wordcount().bytes == 0 end)
          save_undo(item)
          error('An open buffer changed while renaming; keeping its edits')
        end
      end
      if project.root ~= root or not valid_path(source, root) or not valid_path(destination, root)
        or not same(initial, vim.uv.fs_lstat(source))
        or vim.uv.fs_lstat(destination) and not case_alias(source, destination, initial) then error('File or destination changed; rename cancelled') end
      local renamed, message = vim.uv.fs_rename(source, destination)
      if not renamed then error(message or 'Cannot rename entry') end
      moved = true
      for _, item in ipairs(items) do restore(item, item.new, item.loaded) end
      local expanded = {}
      for path, value in pairs(tree.expanded) do expanded[within(path, source) and destination .. path:sub(#source + 1) or path] = value end
      tree.expanded = expanded
      tree.clear_search(); tree.render()
      if tree.is_tree_window(origin) then
        vim.api.nvim_set_current_win(origin)
        for row, value in pairs(tree.rows) do if value.path == destination then vim.api.nvim_win_set_cursor(origin, { row, 0 }); break end end
      end
      require('jetvim.vcs').refresh()
    end)
    if not success then
      local rollback = not moved
      if moved and (not vim.uv.fs_lstat(source) or case_alias(destination, source, initial))
        and valid_path(source, root) and same(initial, vim.uv.fs_lstat(destination)) then
        rollback = vim.uv.fs_rename(destination, source) == true
      end
      for _, item in ipairs(items) do
        local target = rollback and item.old or item.new
        local restored = pcall(restore, item, target, item.loaded)
        if not restored and held[item.buf] then
          -- Preserve dirty text even when native reload/undo restoration failed.
          local recovered = pcall(function()
            vim.bo[item.buf].modifiable = true
            vim.api.nvim_buf_set_lines(item.buf, 0, -1, false, item.empty and {} or item.lines)
            for option, value in pairs(item.options) do vim.bo[item.buf][option] = value end
          end)
          held[item.buf].failed = true
          item.recovery = true
          if not recovered and item.undo then pcall(vim.fn.writefile, { vim.json.encode({ lines = item.lines, options = item.options }) }, item.undo .. '.json') end
          pcall(vim.notify, 'Autosave paused for ' .. item.old
            .. '. Save a copy of your edits and reopen the file before continuing.'
            .. (item.undo and '\nUndo recovery: ' .. item.undo or '')
            .. (not recovered and '\nThe in-memory recovery also failed.' or ''), vim.log.levels.ERROR)
        end
      end
      pcall(vim.notify, 'Cannot rename: ' .. tostring(failure) .. (not rollback and '\nThe file remains at ' .. tostring(destination) or ''), vim.log.levels.WARN)
      pcall(tree.render)
    end
    for _, item in ipairs(items) do
      pcall(reattach, item)
      if item.loaded and vim.api.nvim_buf_is_valid(item.buf) then pcall(function() require('jetvim.blame').refresh(item.buf) end) end
      if item.undo and not item.recovery then pcall(vim.uv.fs_unlink, item.undo) end
    end
    if autosave then autosave.writing = writing end
    if disk then disk.reloading = reloading end
    release()
  end
  local prompted, prompt_error = pcall(vim.ui.input, { prompt = 'Rename: ', default = vim.fs.basename(source) }, accept)
  if not prompted then release(); vim.notify('Cannot rename: ' .. tostring(prompt_error), vim.log.levels.WARN) end
end
return M
