local M = {}
local picker_ns = vim.api.nvim_create_namespace('JetvimPickerAppearance')
-- A prompt buffer and a separate result window keep ordinary typing, arrows,
-- backspace and Escape working without requiring Vim command knowledge.
function M.pick(title, items, accept)
  vim.cmd.stopinsert()
  local origin = vim.api.nvim_get_current_win()
  local width = math.max(20, math.min(90, vim.o.columns - 6))
  local height = math.max(1, math.min(16, vim.o.lines - 10))
  local row = math.max(0, math.floor((vim.o.lines - height - 5) / 3))
  local col = math.max(0, math.floor((vim.o.columns - width) / 2))
  local input = vim.api.nvim_create_buf(false, true)
  local results = vim.api.nvim_create_buf(false, true)
  local listwin = vim.api.nvim_open_win(results, false, {
    relative = 'editor', row = row + 3, col = col, width = width, height = height,
    style = 'minimal', border = 'rounded', focusable = false,
    footer = ' ↑↓ choose · Enter open · Esc cancel ', footer_pos = 'center',
  })
  local promptwin = vim.api.nvim_open_win(input, true, {
    relative = 'editor', row = row, col = col, width = width, height = 1,
    style = 'minimal', border = 'rounded', title = ' ' .. title .. ' ', title_pos = 'center',
  })
  for _, win in ipairs({ listwin, promptwin }) do
    vim.wo[win].winhighlight = 'Normal:JetvimPopup,NormalFloat:JetvimPopup,FloatBorder:JetvimPopupBorder'
  end
  vim.bo[input].buftype = 'prompt'
  vim.bo[input].bufhidden = 'wipe'
  vim.bo[results].bufhidden = 'wipe'
  vim.fn.prompt_setprompt(input, '❯ ')
  local filtered, selected, closed = {}, 1, false
  local function draw()
    if closed then return end
    local query = (vim.api.nvim_buf_get_lines(input, 0, 1, false)[1] or ''):gsub('^❯ ', '')
    local labels, lookup = {}, {}
    for i, item in ipairs(items) do
      local label = type(item) == 'string' and item or item.label
      labels[#labels + 1] = label
      lookup[label] = lookup[label] or {}
      table.insert(lookup[label], i)
    end
    local matches = query == '' and labels or vim.fn.matchfuzzy(labels, query)
    filtered = {}
    for _, label in ipairs(matches) do
      local indices = lookup[label]
      if #indices > 0 then filtered[#filtered + 1] = items[table.remove(indices, 1)] end
    end
    selected = math.max(1, math.min(selected, #filtered))
    local lines = {}
    local first = math.max(1, selected - height + 1)
    for i = first, math.min(#filtered, first + height - 1) do
      local item = filtered[i]
      lines[#lines + 1] = (i == selected and ' › ' or '   ') .. (type(item) == 'string' and item or item.label)
    end
    vim.api.nvim_buf_set_lines(results, 0, -1, false, #lines > 0 and lines or { '   No matches' })
    vim.api.nvim_buf_clear_namespace(results, picker_ns, 0, -1)
    if #filtered > 0 then
      vim.api.nvim_buf_set_extmark(results, picker_ns, selected - first, 0, { line_hl_group = 'JetvimPickerSelected' })
    end
  end
  local function close()
    if closed then return end
    closed = true
    vim.cmd.stopinsert()
    for _, win in ipairs({ promptwin, listwin }) do
      if vim.api.nvim_win_is_valid(win) then vim.api.nvim_win_close(win, true) end
    end
    if vim.api.nvim_win_is_valid(origin) then vim.api.nvim_set_current_win(origin) end
  end
  local function choose()
    local item = filtered[selected]
    close()
    if item then vim.schedule(function() accept(item) end) end
  end
  vim.fn.prompt_setcallback(input, choose)
  for _, mode in ipairs({ 'i', 'n' }) do
    vim.keymap.set(mode, '<Esc>', close, { buffer = input, nowait = true })
    vim.keymap.set(mode, '<CR>', choose, { buffer = input })
    vim.keymap.set(mode, '<Down>', function() selected = math.min(#filtered, selected + 1); draw() end, { buffer = input })
    vim.keymap.set(mode, '<Up>', function() selected = math.max(1, selected - 1); draw() end, { buffer = input })
    vim.keymap.set(mode, '<C-n>', function() selected = math.min(#filtered, selected + 1); draw() end, { buffer = input })
    vim.keymap.set(mode, '<C-p>', function() selected = math.max(1, selected - 1); draw() end, { buffer = input })
  end
  vim.api.nvim_create_autocmd({ 'TextChangedI', 'TextChanged' }, { buffer = input, callback = function() selected = 1; draw() end })
  vim.api.nvim_create_autocmd('WinClosed', { pattern = tostring(promptwin), once = true, callback = function() vim.schedule(close) end })
  draw()
  vim.cmd.startinsert()
end
function M.input(label, callback, default)
  vim.ui.input({ prompt = label .. ': ', default = default }, function(value)
    if value and value ~= '' then callback(value) end
  end)
end
return M
