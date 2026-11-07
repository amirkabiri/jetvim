local M = {}
local picker_ns = vim.api.nvim_create_namespace('JetvimPickerAppearance')
-- A prompt buffer and a separate result window keep ordinary typing, arrows,
-- backspace and Escape working without requiring Vim command knowledge.
function M.pick(title, items, accept, options)
  options = options or {}
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
  local filtered, selected, closed, last_query = {}, 1, false, nil
  local all_selected = false
  local function draw()
    if closed then return end
    local query = (vim.api.nvim_buf_get_lines(input, 0, 1, false)[1] or ''):gsub('^❯ ', '')
    if query ~= last_query then selected, last_query, all_selected = 1, query, false end
    local labels, lookup = {}, {}
    for i, item in ipairs(items) do
      local label = type(item) == 'string' and item or item.label
      labels[#labels + 1] = label
      lookup[label] = lookup[label] or {}
      table.insert(lookup[label], i)
    end
    local match_query = options.transform_query and options.transform_query(query) or query
    local matches = match_query == '' and labels or vim.fn.matchfuzzy(labels, match_query)
    filtered = {}
    for _, label in ipairs(matches) do
      local indices = lookup[label]
      if #indices > 0 then filtered[#filtered + 1] = items[table.remove(indices, 1)] end
    end
    if options.sections then
      local ordered, included = {}, {}
      for _, section in ipairs(options.sections) do
        for index, item in ipairs(filtered) do
          if type(item) == 'table' and item.section == section then
            ordered[#ordered + 1], included[index] = item, true
          end
        end
      end
      for index, item in ipairs(filtered) do
        if not included[index] then ordered[#ordered + 1] = item end
      end
      filtered = ordered
    end
    selected = math.max(1, math.min(selected, #filtered))
    local lines, highlights = {}, {}
    local first = math.max(1, selected - height + 1)
    local function item_line(item, index)
      local prefix = all_selected and ((index == selected and '›' or ' ') .. '✓ ')
        or (index == selected and ' › ' or '   ')
      return prefix .. (type(item) == 'string' and item or item.label)
    end
    if options.sections then
      -- Headings are display rows, never members of the selectable result list.
      local rendered, rows, groups, previous_section = {}, {}, {}, nil
      for index, item in ipairs(filtered) do
        local section = type(item) == 'table' and item.section or nil
        if section and section ~= previous_section then
          rendered[#rendered + 1] = ' ──── ' .. section .. ' ────'
          groups[#rendered] = 'Comment'
        end
        previous_section = section
        rendered[#rendered + 1], rows[index] = item_line(item, index), #rendered + 1
      end
      first = math.max(1, (rows[selected] or 1) - height + 1)
      for row = first, math.min(#rendered, first + height - 1) do
        lines[#lines + 1] = rendered[row]
        if groups[row] then highlights[#lines - 1] = groups[row] end
      end
      for index, row in ipairs(rows) do
        if (all_selected or index == selected) and row >= first and row < first + height then
          highlights[row - first] = 'JetvimPickerSelected'
        end
      end
    else
      for i = first, math.min(#filtered, first + height - 1) do
        lines[#lines + 1] = item_line(filtered[i], i)
        if all_selected or i == selected then highlights[i - first] = 'JetvimPickerSelected' end
      end
    end
    vim.api.nvim_buf_set_lines(results, 0, -1, false, #lines > 0 and lines or { '   No matches' })
    vim.api.nvim_buf_clear_namespace(results, picker_ns, 0, -1)
    for row, group in pairs(highlights) do
      vim.api.nvim_buf_set_extmark(results, picker_ns, row, 0, { line_hl_group = group })
    end
    if options.accept_many then
      local footer = all_selected and (#filtered .. ' selected · Enter open files · edit query clears selection · Esc cancel')
        or '↑↓ choose · ⌘A select all · Enter open · Esc cancel'
      vim.api.nvim_win_set_config(listwin, { footer = ' ' .. footer .. ' ', footer_pos = 'center' })
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
  local choosing = false
  local function choose()
    if closed or choosing then return end
    choosing = true
    -- Native bracketed paste is delivered as an RPC event. An Enter in the
    -- same terminal packet can run first; keep its prompt alive until pending
    -- paste events have inserted their text, then resolve the actual query.
    vim.schedule(function()
      if closed then return end
      draw()
      local item = filtered[selected]
      local many = all_selected and vim.list_slice(filtered) or nil
      local query = last_query
      close()
      local function accepted()
        if many and #many > 0 then options.accept_many(many)
        elseif item then accept(item, query) end
      end
      -- stopinsert takes effect when the input loop resumes. Running an action
      -- which starts Insert before that boundary would immediately leave it.
      if vim.fn.mode():sub(1, 1) == 'i' then
        vim.api.nvim_create_autocmd('InsertLeave', { once = true, callback = function() vim.schedule(accepted) end })
      else
        vim.schedule(accepted)
      end
    end)
  end
  vim.fn.prompt_setcallback(input, choose)
  for _, mode in ipairs({ 'i', 'n' }) do
    vim.keymap.set(mode, '<Esc>', close, { buffer = input, nowait = true })
    vim.keymap.set(mode, '<CR>', choose, { buffer = input })
    vim.keymap.set(mode, '<Down>', function() all_selected = false; selected = math.min(#filtered, selected + 1); draw() end, { buffer = input })
    vim.keymap.set(mode, '<Up>', function() all_selected = false; selected = math.max(1, selected - 1); draw() end, { buffer = input })
    vim.keymap.set(mode, '<C-n>', function() all_selected = false; selected = math.min(#filtered, selected + 1); draw() end, { buffer = input })
    vim.keymap.set(mode, '<C-p>', function() all_selected = false; selected = math.max(1, selected - 1); draw() end, { buffer = input })
    if options.accept_many then
      local function select_all()
        -- Draw first so text and Command-A arriving in one packet select the
        -- actual filtered results rather than an older TextChangedI snapshot.
        draw()
        all_selected = #filtered > 0
        draw()
      end
      vim.keymap.set(mode, '<D-a>', select_all, { buffer = input, silent = true })
      for index, binding in ipairs(require('jetvim.keymap').bindings or {}) do
        if binding.id == 'select_all' then
          vim.keymap.set(mode, vim.fn.nr2char(0xF0000 + index), select_all, { buffer = input, silent = true })
          break
        end
      end
    end
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
