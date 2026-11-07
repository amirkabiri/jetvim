-- Optional read-only blame annotations. Cursor movement only redraws cached data.
local M = { states = {} }
local function config() return (require('jetvim.settings').get().git or {}).blame or { enabled = true, mode = 'current_line' } end
local function clear(buf)
  if vim.api.nvim_buf_is_valid(buf) then require('jetvim.api').annotations('git-blame', buf, {}) end
end
local function eligible(buf)
  return config().enabled and vim.env.JETVIM_DISABLE_VCS ~= '1' and vim.api.nvim_buf_is_valid(buf)
    and vim.api.nvim_buf_is_loaded(buf) and vim.bo[buf].buftype == '' and require('jetvim.project').resolve(vim.api.nvim_buf_get_name(buf))
end
function M.parse(output)
  local lines, details, record = {}, {}, {}
  for line in (output .. '\n'):gmatch('(.-)\n') do
    local hash, row = line:match('^(%x+) %d+ (%d+)')
    if hash then record = { hash = hash, row = tonumber(row) }
    elseif line:sub(1, 7) == 'author ' then record.author = line:sub(8)
    elseif line:sub(1, 12) == 'author-time ' then record.time = tonumber(line:sub(13))
    elseif line:sub(1, 8) == 'summary ' then record.summary = line:sub(9)
    elseif line:sub(1, 1) == '\t' and record.row then
      lines[record.row] = record.hash:match('^0+$') and 'Uncommitted changes'
        or (record.author or 'Unknown') .. ' · ' .. (record.summary or '')
      details[record.row] = { hash = record.hash, author = record.author, summary = record.summary, time = record.time }
      record = {}
    end
  end
  return lines, details
end
function M.render(buf)
  buf = buf or vim.api.nvim_get_current_buf()
  local state = M.states[buf]
  -- Fresh tool buffers have never owned a blame annotation to clear.
  if not state then return end
  if not eligible(buf) or state.tick ~= vim.api.nvim_buf_get_changedtick(buf) then clear(buf); return end
  local entries = {}
  if config().mode == 'all' then
    for line, text in pairs(state.lines or {}) do entries[#entries + 1] = { line = line, text = '  ' .. text } end
  else
    local row = vim.api.nvim_get_current_buf() == buf and vim.api.nvim_win_get_cursor(0)[1]
    if row and state.lines and state.lines[row] then entries[1] = { line = row, text = '  ' .. state.lines[row] } end
  end
  require('jetvim.api').annotations('git-blame', buf, entries)
end
local function cancel(buf)
  local state = M.states[buf]
  if state and state.job then pcall(state.job.kill, state.job, 15) end
  M.states[buf] = nil
end
function M.refresh(buf)
  buf = buf or vim.api.nvim_get_current_buf()
  cancel(buf); clear(buf)
  local path = eligible(buf)
  if not path or vim.fn.executable('git') ~= 1 then return end
  local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
  local text = table.concat(lines, '\n') .. (vim.bo[buf].endofline and '\n' or '')
  if #text > 1024 * 1024 or text:find('\0', 1, true) then return end
  local state = { path = path, tick = vim.api.nvim_buf_get_changedtick(buf) }
  M.states[buf] = state
  -- Git accepts absolute paths inside the selected repository, including a
  -- selected subdirectory. --contents includes unsaved edits without disk writes.
  local argv = { 'git', '--no-pager', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-C', require('jetvim.project').root,
    'blame', '--line-porcelain', '--contents', '-', '--', path }
  vim.defer_fn(function()
    if M.states[buf] ~= state or not eligible(buf) then return end
    local ok, job = pcall(vim.system, argv, { stdin = text, text = true, timeout = 10000 }, function(result)
      vim.schedule(function()
        if M.states[buf] ~= state or not eligible(buf) or state.tick ~= vim.api.nvim_buf_get_changedtick(buf) then return end
        state.job = nil
        if result.code == 0 then state.lines, state.details = M.parse(result.stdout or ''); M.render(buf) end
      end)
    end)
    if ok then state.job = job end
  end, 300)
end
function M.setup()
  local group = vim.api.nvim_create_augroup('JetvimBlame', { clear = true })
  vim.api.nvim_create_autocmd({ 'BufEnter', 'BufReadPost', 'BufWritePost', 'TextChanged', 'TextChangedI', 'FocusGained' }, { group = group, callback = function(event) M.refresh(event.buf) end })
  vim.api.nvim_create_autocmd({ 'CursorMoved', 'CursorMovedI' }, { group = group, callback = function(event) M.render(event.buf) end })
  vim.api.nvim_create_autocmd('User', { group = group, pattern = { 'JetvimSettingsChanged', 'JetvimVcsChanged' }, callback = function()
    for _, buf in ipairs(vim.api.nvim_list_bufs()) do M.refresh(buf) end
  end })
  vim.api.nvim_create_autocmd('BufWipeout', { group = group, callback = function(event) cancel(event.buf) end })
  vim.api.nvim_create_autocmd('VimLeavePre', { group = group, callback = function() for buf in pairs(M.states) do cancel(buf) end end })
  vim.api.nvim_create_user_command('JetvimBlameInfo', function()
    local state = M.states[vim.api.nvim_get_current_buf()]
    local row = vim.api.nvim_win_get_cursor(0)[1]
    local detail = state and state.tick == vim.api.nvim_buf_get_changedtick(0) and state.details and state.details[row]
    if not detail then vim.notify('No blame information for this line'); return end
    if detail.hash:match('^0+$') then vim.notify('Uncommitted changes'); return end
    local date = detail.time and os.date('%Y-%m-%d %H:%M', detail.time) or ''
    vim.notify(table.concat({ detail.hash, (detail.author or 'Unknown') .. ' · ' .. date, detail.summary or '' }, '\n'), vim.log.levels.INFO, { title = 'Git blame' })
  end, { desc = 'Show current line commit details' })
  M.refresh()
end
return M
