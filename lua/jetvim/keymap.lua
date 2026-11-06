local M = {}
-- Query buffers contain only user text; their visible prefix is virtual text.
-- Native Insert-mode CtrlW edits synchronously and cannot strand the field in
-- Normal mode before the next character in the same terminal input batch.
function M.input_word_delete(buf)
  local options = { buffer = buf, silent = true, desc = 'Delete Previous Word' }
  vim.keymap.set('i', '<M-BS>', '<C-w>', options)
  vim.keymap.set('i', '<M-C-h>', '<C-w>', options)
  for index, binding in ipairs(M.bindings or {}) do
    if binding.id == 'delete_word_left' then
      vim.keymap.set('i', binding.key, '<C-w>', options)
      vim.keymap.set('i', vim.fn.nr2char(0xF0000 + index), '<C-w>', options)
      break
    end
  end
end
function M.setup(root)
  M.bindings = vim.json.decode(table.concat(vim.fn.readfile(root .. '/config/keymap.json'), '\n'))
  local actions = require('jetvim.actions')
  -- Deferred insert-mode actions retain input order. Later shortcuts resolve
  -- their target after the preceding action has opened/switched its pane.
  local pending, running = {}, false
  local function completed()
    running = false
    local next_action = table.remove(pending, 1)
    if next_action then next_action() end
  end
  local bindings = vim.deepcopy(M.bindings)
  local function selecting(id)
    return id:match('^select_') or id == 'extend_selection' or id == 'shrink_selection'
  end
  -- Insert-mode selection shortcuts finish synchronously before printable
  -- typeahead. The explicit caret survives the native Insert->Normal transition.
  M.insert_selection = function(id, buf, win, row, col)
    if not selecting(id) or vim.api.nvim_get_current_buf() ~= buf
      or vim.api.nvim_get_current_win() ~= win then return end
    local ok, err = pcall(function()
      vim.api.nvim_win_set_cursor(win, { row, col })
      actions[id]()
    end)
    if not ok then vim.notify('Selection: ' .. tostring(err), vim.log.levels.ERROR) end
    if vim.fn.mode() == 'n' and vim.bo.modifiable and not vim.bo.readonly
      and (vim.bo.buftype == '' or vim.bo.buftype == 'prompt'
        or vim.bo.filetype == 'jetvim-search' or vim.bo.filetype == 'jetvim-project-search') then
      vim.cmd.startinsert()
    end
  end
  -- Fn+Up/Down are already translated to standard PageUp/PageDown keys by
  -- terminals. Use the common dispatcher without adding macOS bridge chords.
  vim.list_extend(bindings, {
    { id = 'page_up', label = 'Page Up', key = '<PageUp>', native_only = true },
    { id = 'page_down', label = 'Page Down', key = '<PageDown>', native_only = true },
    { id = 'select_page_up', label = 'Select Page Up', key = '<S-PageUp>', native_only = true },
    { id = 'select_page_down', label = 'Select Page Down', key = '<S-PageDown>', native_only = true },
    { id = 'select_home', label = 'Select to Line Start', key = '<S-Home>', native_only = true },
    { id = 'select_end', label = 'Select to Line End', key = '<S-End>', native_only = true },
  })
  for index, binding in ipairs(bindings) do
    assert(actions[binding.id], 'Missing action: ' .. binding.id)
    local function invoke()
      if running then pending[#pending + 1] = invoke; return end
      running = true
      local mode = vim.fn.mode()
      local typing = mode == 'i' or mode == 's' or mode == 'S'
      local buf, win = vim.api.nvim_get_current_buf(), vim.api.nvim_get_current_win()
      local caret = vim.api.nvim_win_get_cursor(win)
      local function execute()
        if vim.api.nvim_get_current_buf() ~= buf or vim.api.nvim_get_current_win() ~= win then completed(); return end
        if mode == 'i' then vim.api.nvim_win_set_cursor(win, caret) end
        local ok, err = pcall(actions[binding.id])
        if not ok then vim.notify(binding.label .. ': ' .. tostring(err), vim.log.levels.ERROR) end
        if typing then
          vim.schedule(function()
            local same_buffer = vim.api.nvim_get_current_buf() == buf
            local switched_editor = binding.id == 'next_tab' or binding.id == 'previous_tab'
            if (same_buffer or switched_editor) and vim.api.nvim_get_current_win() == win
              and vim.bo.buftype == '' and vim.fn.mode() == 'n' and binding.id ~= 'vim_mode' then
              vim.cmd.startinsert()
            end
          end)
        end
        completed()
      end
      if mode == 'i' then
        -- Finish leaving insert mode before changing cursor/selection: Vim
        -- otherwise applies its deferred cursor adjustment after our action.
        vim.cmd.stopinsert()
        vim.schedule(execute)
      else execute() end
    end
    local opts = { silent = true, desc = binding.label }
    local function bind(key)
      vim.keymap.set({ 'n', 'i', 'x', 's' }, key, invoke, opts)
      if selecting(binding.id) then
        vim.keymap.set('i', key, function()
          if running then pending[#pending + 1] = invoke; return '' end
          local cursor = vim.api.nvim_win_get_cursor(0)
          return string.format([[<C-\><C-n><Cmd>lua require('jetvim.keymap').insert_selection(%q,%d,%d,%d,%d)<CR>]],
            binding.id, vim.api.nvim_get_current_buf(), vim.api.nvim_get_current_win(), cursor[1], cursor[2])
        end, { expr = true, silent = true, desc = binding.label })
      end
    end
    bind(binding.key)
    for _, alias in ipairs(binding.aliases or {}) do
      bind(alias.key)
      for _, key in ipairs(alias.alternate_keys or {}) do
        bind(key)
      end
    end
    -- A dedicated terminal profile sends these sequences even when the terminal
    -- would normally consume Command shortcuts. No global preferences change.
    local relay = not binding.native_only and vim.fn.nr2char(0xF0000 + index) or nil
    if relay then bind(relay) end
    if binding.fallback then vim.keymap.set('n', binding.fallback, invoke, opts) end
    if binding.id == 'close' or binding.id == 'tree_new' then
      -- Editor-tab close and tree-only creation never reach terminal input.
      -- A terminal has no editor tab of its own, so keep its focus/mode intact.
      vim.keymap.set('t', binding.key, '<Nop>', opts)
      if relay then vim.keymap.set('t', relay, '<Nop>', opts) end
    elseif binding.id == 'delete_word_left' then
      -- Both Option keys use the same Alt modifier. Send one portable shell
      -- backward-word command instead of forwarding a CSI-u/private relay key.
      vim.keymap.set('t', binding.key, '<C-w>', opts)
      vim.keymap.set('t', '<M-C-h>', '<C-w>', opts)
      if relay then vim.keymap.set('t', relay, '<C-w>', opts) end
    elseif binding.id == 'terminal' or binding.id == 'editor' or binding.id == 'tree' or binding.id == 'git_changes' then
      -- Complete the terminal-to-normal transition before dispatching. Queuing
      -- feedkeys and a separate scheduled callback can race with window changes.
      local rhs = [[<C-\><C-n><Cmd>lua require('jetvim.actions').]] .. binding.id .. [[()<CR>]]
      vim.keymap.set('t', binding.key, rhs, opts)
      vim.keymap.set('t', relay, rhs, opts)
    elseif binding.id:match('^resize_') then
      -- Resize the terminal's pane without forwarding the shortcut to its
      -- process; return to terminal input after the synchronous resize action.
      local rhs = [[<C-\><C-n><Cmd>lua require('jetvim.actions').]] .. binding.id .. [[()<CR>i]]
      vim.keymap.set('t', binding.key, rhs, opts)
      vim.keymap.set('t', relay, rhs, opts)
    end
  end
  -- Ordinary arrows collapse typing selections to their relevant boundary;
  -- explicit Vim Visual mode keeps its native arrow movement.
  for key, motion in pairs({ ['<Up>'] = 'k', ['<Left>'] = 'h', ['<Down>'] = 'j', ['<Right>'] = 'l' }) do
    local ending = key == '<Down>' or key == '<Right>'
    vim.keymap.set('s', key, function() require('jetvim.edit').collapse_selection(ending, key) end,
      { silent = true, desc = 'Collapse Selection' })
    vim.keymap.set('x', key, motion, { silent = true, desc = 'Extend Visual Selection' })
  end
  vim.keymap.set({ 'n', 'i', 'x', 's' }, '<F1>', actions.documentation, { desc = 'Quick Documentation' })
  vim.keymap.set('i', '<Tab>', function()
    return vim.fn.pumvisible() == 1 and '<C-n>' or '<Tab>'
  end, { expr = true })
  vim.keymap.set('i', '<S-Tab>', function()
    return vim.fn.pumvisible() == 1 and '<C-p>' or '<C-d>'
  end, { expr = true })
  vim.keymap.set({ 'x', 's' }, '<Tab>', actions.indent)
  vim.keymap.set({ 'x', 's' }, '<S-Tab>', actions.unindent)
end
return M
