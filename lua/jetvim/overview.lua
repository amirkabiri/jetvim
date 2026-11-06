-- Whole-file diagnostic positions on the editor's right edge. Floats overlay
-- one existing text column; they never participate in the split layout.
local M = { panes = {} }
local ns = vim.api.nvim_create_namespace('JetvimDiagnosticOverview')
local groups = { 'JetvimOverviewError', 'JetvimOverviewWarning', 'JetvimOverviewInfo', 'JetvimOverviewHint' }
local function valid(win) return win and vim.api.nvim_win_is_valid(win) end
local function editor(win)
  if not valid(win) or vim.api.nvim_win_get_config(win).relative ~= '' then return false end
  local buf = vim.api.nvim_win_get_buf(win)
  return vim.bo[buf].buftype == '' and vim.bo[buf].buflisted and vim.api.nvim_buf_get_name(buf) ~= ''
end
local function remove(owner)
  local pane = M.panes[owner]
  M.panes[owner] = nil
  if pane and valid(pane.win) then vim.api.nvim_win_close(pane.win, true) end
end
function M.cells(buf, height)
  local cells, count = {}, vim.api.nvim_buf_line_count(buf)
  local function row(line)
    return math.floor(math.max(0, math.min(count - 1, line)) * (height - 1) / math.max(1, count - 1))
  end
  for _, diagnostic in ipairs(vim.diagnostic.get(buf)) do
    local severity = diagnostic.severity or vim.diagnostic.severity.ERROR
    if groups[severity] then
      for index = row(diagnostic.lnum), row(diagnostic.end_lnum or diagnostic.lnum) do
        if not cells[index] or severity < cells[index].severity then
          cells[index] = { severity = severity, line = diagnostic.lnum + 1, col = diagnostic.col or 0 }
        end
      end
    end
  end
  return cells
end
local function jump(owner, pane, mouse, typing)
  mouse = mouse or vim.fn.getmousepos()
  if typing == nil then typing = vim.fn.mode() == 'i' end
  local target, distance
  for row, cell in pairs(pane.cells) do
    local delta = math.abs(row - (mouse.winrow - 1))
    if not distance or delta < distance then target, distance = cell, delta end
  end
  if not target then return end
  vim.cmd.stopinsert()
  vim.schedule(function()
    if not editor(owner) or vim.api.nvim_win_get_buf(owner) ~= pane.source then return end
    vim.api.nvim_set_current_win(owner)
    local row = math.min(target.line, vim.api.nvim_buf_line_count(pane.source))
    local line = vim.api.nvim_buf_get_lines(pane.source, row - 1, row, false)[1] or ''
    vim.api.nvim_win_set_cursor(owner, { row, math.min(target.col, #line) })
    vim.cmd.normal({ args = { 'zvzz' }, bang = true })
    if typing then vim.cmd.startinsert() end
    M.schedule()
  end)
end
local function render(owner)
  local source = vim.api.nvim_win_get_buf(owner)
  local height, width = vim.api.nvim_win_get_height(owner), vim.api.nvim_win_get_width(owner)
  local cells = M.cells(source, height)
  if not next(cells) then remove(owner); return end
  local pane = M.panes[owner]
  local config = { relative = 'win', win = owner, row = 0, col = width - 1,
    width = 1, height = height, focusable = false, style = 'minimal', zindex = 40, mouse = true }
  if not pane or not valid(pane.win) then
    pane = { buf = vim.api.nvim_create_buf(false, true), source = source }
    vim.bo[pane.buf].bufhidden = 'wipe'
    vim.bo[pane.buf].filetype = 'jetvim-overview'
    local initial = vim.tbl_extend('force', config, { noautocmd = true, mouse = true })
    local ok, win = pcall(vim.api.nvim_open_win, pane.buf, false, initial)
    -- Older supported Neovim builds may lack the optional mouse field.
    if not ok then initial.mouse = nil; win = vim.api.nvim_open_win(pane.buf, false, initial) end
    pane.clickable = ok
    pane.win = win
    M.panes[owner] = pane
    vim.w[win].jetvim_overview = true
    vim.wo[win].winhighlight = 'Normal:JetvimOverviewBackground,NormalFloat:JetvimOverviewBackground,EndOfBuffer:JetvimOverviewBackground'
    vim.wo[win].signcolumn = 'no'
    vim.wo[win].wrap = false
    for _, mode in ipairs({ 'n', 'i' }) do
      vim.keymap.set(mode, '<LeftMouse>', function() jump(owner, pane) end, { buffer = pane.buf, silent = true })
    end
  else
    if not pane.clickable then config.mouse = nil end
    vim.api.nvim_win_set_config(pane.win, config)
  end
  pane.source, pane.cells = source, cells
  local lines = {}
  for row = 0, height - 1 do lines[#lines + 1] = cells[row] and '█' or ' ' end
  vim.bo[pane.buf].modifiable = true
  vim.api.nvim_buf_set_lines(pane.buf, 0, -1, false, lines)
  vim.api.nvim_buf_clear_namespace(pane.buf, ns, 0, -1)
  for row, cell in pairs(cells) do
    vim.api.nvim_buf_set_extmark(pane.buf, ns, row, 0, { end_col = #'█', hl_group = groups[cell.severity] })
  end
  vim.bo[pane.buf].modifiable = false
  vim.bo[pane.buf].modified = false
end
function M.refresh()
  if M.stopping then return end
  local current = vim.api.nvim_get_current_win()
  local eligible = {}
  -- Tool/prompt focus hides the overview without moving focus or the caret.
  if editor(current) then
    for _, win in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
      if editor(win) then eligible[win] = true end
    end
  end
  for owner in pairs(M.panes) do if not eligible[owner] then remove(owner) end end
  for owner in pairs(eligible) do render(owner) end
end
function M.schedule()
  if M.pending or M.stopping then return end
  M.pending = true
  vim.schedule(function() M.pending = false; M.refresh() end)
end
function M.setup()
  M.stopping = false
  local group = vim.api.nvim_create_augroup('JetvimDiagnosticOverview', { clear = true })
  -- Mouse mappings are resolved before Nvim moves into the clicked window, so
  -- dispatch known stripe hits here and pass every other click through normally.
  vim.keymap.set({ 'n', 'i' }, '<LeftMouse>', function()
    local mouse, typing = vim.fn.getmousepos(), vim.fn.mode() == 'i'
    for owner, pane in pairs(M.panes) do
      if mouse.winid == pane.win then
        vim.schedule(function() jump(owner, pane, mouse, typing) end)
        return ''
      end
    end
    return '<LeftMouse>'
  end, { expr = true, silent = true })
  vim.api.nvim_create_autocmd({ 'DiagnosticChanged', 'BufWinEnter', 'BufEnter', 'WinEnter', 'WinLeave',
    'WinResized', 'VimResized', 'WinClosed', 'TabEnter', 'TextChanged', 'TextChangedI', 'BufWipeout' },
    { group = group, callback = M.schedule })
  vim.api.nvim_create_autocmd('VimLeavePre', { group = group, callback = function()
    M.stopping = true
    for owner in pairs(M.panes) do remove(owner) end
  end })
  M.schedule()
end
return M
