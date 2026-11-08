-- In-file text/regex search: one row over the active editor, never a layout split.
local M = { query = '', matches = {}, selected = 0 }
local ns = vim.api.nvim_create_namespace('JetvimSearch')
local label_ns = vim.api.nvim_create_namespace('JetvimSearchInput')
local lifecycle, pending_leave = 0, nil
local function invalidate_resume()
  lifecycle = lifecycle + 1
  if pending_leave then pcall(vim.api.nvim_del_autocmd, pending_leave); pending_leave = nil end
end
local function valid(win) return win and vim.api.nvim_win_is_valid(win) end
local function source() return valid(M.owner) and vim.api.nvim_win_get_buf(M.owner) == M.source end
local function clear()
  if M.source and vim.api.nvim_buf_is_valid(M.source) then vim.api.nvim_buf_clear_namespace(M.source, ns, 0, -1) end
end
function M.pattern(query)
  local expression, flags, regex = query, '', false
  if query:sub(1, 1) == '/' then
    local ending
    for i = #query, 2, -1 do
      if query:sub(i, i) == '/' then
        local slashes, j = 0, i - 1
        while j > 0 and query:sub(j, j) == '\\' do slashes, j = slashes + 1, j - 1 end
        if slashes % 2 == 0 then ending = i; break end
      end
    end
    if ending then
      regex = true
      expression, flags = query:sub(2, ending - 1), query:sub(ending + 1)
      if flags ~= '' and flags ~= 'i' then return nil, 'Invalid regex flag (use i)' end
      expression = expression:gsub('\\/', '/')
    end
  end
  local pattern = regex and ((flags == 'i' and [[\c\v]] or [[\C\v]]) .. expression)
    or ([[\c\V]] .. query:gsub('\\', '\\\\'))
  local ok, err = pcall(vim.regex, pattern)
  if not ok then return nil, 'Invalid regex: ' .. tostring(err):gsub('[\r\n]', ' ') end
  return pattern
end
local function status()
  if not M.status_buf or not vim.api.nvim_buf_is_valid(M.status_buf) then return end
  local text = M.error or (M.query == '' and 'Text · /…/ regex' or
    (#M.matches == 0 and 'No matches' or string.format('%d/%d%s · Enter next', M.selected, #M.matches, M.limited and '+' or '')))
  vim.api.nvim_buf_set_lines(M.status_buf, 0, -1, false, { ' ' .. text })
end
local function current_mark()
  clear()
  if not source() then return end
  for i, match in ipairs(M.matches) do
    vim.api.nvim_buf_set_extmark(M.source, ns, match.row - 1, match.col, {
      end_col = match.finish, hl_group = i == M.selected and 'IncSearch' or 'Search',
      priority = 180, strict = false,
    })
  end
end
local function reveal()
  local match = M.matches[M.selected]
  if match and source() then
    vim.api.nvim_win_set_cursor(M.owner, { match.row, match.col })
    vim.api.nvim_win_call(M.owner, function() vim.cmd.normal({ args = { 'zvzz' }, bang = true }) end)
  end
  current_mark(); status()
end
function M.update()
  if not source() then M.close(); return end
  if M.input and vim.api.nvim_buf_is_valid(M.input) then M.query = vim.api.nvim_buf_get_lines(M.input, 0, 1, false)[1] or '' end
  M.matches, M.selected, M.error, M.limited = {}, 0, nil, false
  clear()
  if M.query == '' then status(); return end
  local pattern, err = M.pattern(M.query)
  if not pattern then M.error = err; status(); return end
  M.compiled = pattern
  local cursor = M.anchor or vim.api.nvim_win_get_cursor(M.owner)
  local bytes = 0
  for row, line in ipairs(vim.api.nvim_buf_get_lines(M.source, 0, -1, false)) do
    bytes = bytes + #line
    if bytes > 2 * 1024 * 1024 then M.limited = true; break end
    local offset = 0
    while offset <= #line do
      local ok, match = pcall(vim.fn.matchstrpos, line, pattern, offset, 1)
      if not ok then M.error = 'Invalid regex'; M.matches = {}; status(); return end
      if match[2] < 0 then break end
      M.matches[#M.matches + 1] = { row = row, col = match[2], finish = match[3] }
      if M.selected == 0 and (row > cursor[1] or row == cursor[1] and match[2] >= cursor[2]) then M.selected = #M.matches end
      if #M.matches >= 5000 then M.limited = true; break end
      -- Zero-width matches must advance a whole UTF-8 character.
      offset = match[3]
      if match[3] == match[2] then
        if offset == #line then break end
        offset = offset + #vim.fn.strcharpart(line:sub(offset + 1), 0, 1)
      end
    end
    if M.limited then break end
  end
  if #M.matches > 0 and M.selected == 0 then M.selected = 1 end
  vim.fn.setreg('/', pattern)
  reveal()
end
function M.step(direction)
  if valid(M.win) then
    vim.schedule(function()
      if valid(M.win) and vim.api.nvim_get_current_win() == M.win then vim.cmd.startinsert() end
    end)
    local query = vim.api.nvim_buf_get_lines(M.input, 0, 1, false)[1] or ''
    if query ~= M.query then M.update() end
  elseif not source() or vim.api.nvim_get_current_win() ~= M.owner then
    local pattern = vim.fn.getreg('/')
    if pattern ~= '' then pcall(vim.fn.search, pattern, direction < 0 and 'bw' or 'w') end
    return
  end
  if not valid(M.win) then
    local cursor = vim.api.nvim_win_get_cursor(M.owner)
    M.anchor = cursor; M.update()
    vim.api.nvim_win_set_cursor(M.owner, cursor)
  end
  if M.error or #M.matches == 0 then return end
  local cursor = vim.api.nvim_win_get_cursor(M.owner)
  local target
  for i, match in ipairs(M.matches) do
    if direction > 0 and (match.row > cursor[1] or match.row == cursor[1] and match.col > cursor[2]) then target = i; break end
    if direction < 0 and (match.row < cursor[1] or match.row == cursor[1] and match.col < cursor[2]) then target = i end
  end
  M.selected = target or (direction > 0 and 1 or #M.matches)
  reveal()
end
function M.close()
  if M.closing or not M.input and not valid(M.win) then return end
  local focus = valid(M.win) and vim.api.nvim_get_current_win() == M.win
  invalidate_resume()
  local serial = lifecycle
  local leaving = focus and vim.fn.mode() == 'i'
  M.closing = true
  local had_search = M.input ~= nil
  local owner, typing = M.owner, M.typing
  local owner_buf = valid(owner) and vim.api.nvim_win_get_buf(owner)
  local owner_tick = owner_buf and vim.api.nvim_buf_get_changedtick(owner_buf)
  local owner_cursor = valid(owner) and vim.api.nvim_win_get_cursor(owner)
  local function resume()
    if lifecycle == serial and not M.win and focus and valid(owner)
      and vim.api.nvim_get_current_win() == owner and vim.api.nvim_win_get_buf(owner) == owner_buf
      and vim.api.nvim_buf_get_changedtick(owner_buf) == owner_tick
      and typing and vim.bo.modifiable then
      if leaving then vim.api.nvim_win_set_cursor(owner, owner_cursor) end
      vim.cmd.startinsert()
    end
  end
  if leaving then
    vim.cmd.stopinsert()
    pending_leave = vim.api.nvim_create_autocmd('InsertLeave', { once = true, callback = function()
      pending_leave = nil
      vim.schedule(resume)
    end })
  end
  local windows, buffers = { M.win, M.status_win }, { M.input, M.status_buf }
  M.win, M.status_win, M.input, M.status_buf = nil, nil, nil, nil
  for _, win in pairs(windows) do if valid(win) then pcall(vim.api.nvim_win_close, win, true) end end
  for _, buf in pairs(buffers) do if vim.api.nvim_buf_is_valid(buf) then pcall(vim.api.nvim_buf_delete, buf, { force = true }) end end
  clear()
  -- Keep the last pattern for CmdG/n without leaving native Search highlights.
  -- :nohlsearch resets the current display state, not the user's hlsearch option.
  if had_search then vim.cmd.nohlsearch() end
  M.closing = false
  if focus and valid(owner) then
    vim.api.nvim_set_current_win(owner)
  end
  if not leaving then resume() end
end
function M.geometry()
  if not valid(M.win) or not source() then return end
  local width = vim.api.nvim_win_get_width(M.owner)
  local info = math.min(28, math.max(8, math.floor(width / 3)))
  local input = math.max(1, width - info)
  vim.api.nvim_win_set_config(M.win, { relative = 'win', win = M.owner, row = 0, col = 0, width = input, height = 1 })
  vim.api.nvim_win_set_config(M.status_win, { relative = 'win', win = M.owner, row = 0, col = input, width = info, height = 1 })
end
function M.open()
  if valid(M.win) then vim.api.nvim_set_current_win(M.win); vim.cmd.startinsert(); return end
  M.close()
  local restarting = pending_leave ~= nil and vim.fn.mode() == 'i'
  invalidate_resume()
  require('jetvim.tree').editor()
  if vim.bo.buftype ~= '' then return end
  M.owner, M.source = vim.api.nvim_get_current_win(), vim.api.nvim_get_current_buf()
  -- The shared key dispatcher finishes insert mode before calling an action.
  -- Search fields return to ordinary editor typing, matching Jetvim's default.
  M.typing = true
  M.anchor = vim.api.nvim_win_get_cursor(M.owner)
  M.input, M.status_buf = vim.api.nvim_create_buf(false, true), vim.api.nvim_create_buf(false, true)
  for _, buf in ipairs({ M.input, M.status_buf }) do
    vim.bo[buf].bufhidden, vim.bo[buf].filetype = 'wipe', 'jetvim-search'
  end
  vim.api.nvim_buf_set_lines(M.input, 0, -1, false, { M.query })
  M.win = vim.api.nvim_open_win(M.input, true, { relative = 'win', win = M.owner, row = 0, col = 0, width = 1, height = 1, style = 'minimal', zindex = 70 })
  M.status_win = vim.api.nvim_open_win(M.status_buf, false, { relative = 'win', win = M.owner, row = 0, col = 1, width = 1, height = 1, style = 'minimal', focusable = false, zindex = 70 })
  for _, win in ipairs({ M.win, M.status_win }) do vim.wo[win].winhighlight = 'Normal:JetvimPopup,NormalFloat:JetvimPopup' end
  vim.api.nvim_buf_set_extmark(M.input, label_ns, 0, 0, { virt_text = { { 'Find › ', 'JetvimMuted' } }, virt_text_pos = 'inline', right_gravity = false })
  require('jetvim.keymap').input_word_delete(M.input)
  for _, mode_name in ipairs({ 'i', 'n' }) do
    vim.keymap.set(mode_name, '<Esc>', M.close, { buffer = M.input, nowait = true })
    vim.keymap.set(mode_name, '<CR>', function() M.step(1) end, { buffer = M.input })
    vim.keymap.set(mode_name, '<S-CR>', function() M.step(-1) end, { buffer = M.input })
  end
  local group = vim.api.nvim_create_augroup('JetvimSearch', { clear = true })
  vim.api.nvim_create_autocmd({ 'TextChangedI', 'TextChanged' }, { group = group, buffer = M.input, callback = M.update })
  vim.api.nvim_create_autocmd({ 'WinResized', 'VimResized', 'WinScrolled' }, { group = group, callback = M.geometry })
  vim.api.nvim_create_autocmd({ 'BufEnter', 'WinClosed' }, { group = group, callback = function()
    vim.schedule(function()
      if M.win and (not source() or not valid(M.win) or (vim.api.nvim_get_current_buf() ~= M.input and vim.api.nvim_get_current_win() ~= M.owner)) then M.close() end
    end)
  end })
  M.geometry(); M.update()
  vim.api.nvim_win_set_cursor(M.win, { 1, #M.query })
  vim.cmd.startinsert({ bang = true })
  if restarting then
    local serial, win = lifecycle, M.win
    pending_leave = vim.api.nvim_create_autocmd('InsertLeave', { once = true, callback = function()
      pending_leave = nil
      vim.schedule(function()
        if lifecycle == serial and M.win == win and valid(win) and vim.api.nvim_get_current_win() == win then vim.cmd.startinsert({ bang = true }) end
      end)
    end })
  end
end
return M
