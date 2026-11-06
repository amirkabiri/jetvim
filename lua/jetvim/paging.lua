local M = { states = {} }

local function preferred_column()
  -- virtcol(..., true) returns the first/last display cells of a character.
  -- Use its first cell so tabs and wide Unicode characters keep a visual column.
  local columns = vim.fn.virtcol('.', true)
  return math.max(0, columns[1] - 1)
end

function M.move(direction)
  assert(direction == -1 or direction == 1, 'Page direction must be -1 or 1')
  local win, buf = vim.api.nvim_get_current_win(), vim.api.nvim_get_current_buf()
  local cursor, tick = vim.api.nvim_win_get_cursor(win), vim.api.nvim_buf_get_changedtick(buf)
  local state = M.states[win]
  local preferred = preferred_column()
  if state and state.buf == buf and state.tick == tick and vim.deep_equal(state.cursor, cursor) then
    preferred = state.preferred
  end

  -- Keep two rows of overlap, like a conventional full-page editor movement.
  -- Clamp the caret explicitly: Vim's native page scroll may otherwise leave
  -- line 2 selected when the viewport has already reached the top.
  local step = math.max(1, vim.api.nvim_win_get_height(win) - 2)
  local last = vim.api.nvim_buf_line_count(buf)
  local target = math.max(1, math.min(last, cursor[1] + direction * step))
  local line = vim.api.nvim_buf_get_lines(buf, target - 1, target, false)[1] or ''
  local column
  if preferred >= vim.fn.strdisplaywidth(line) then column = #line
  else column = math.max(0, vim.fn.virtcol2col(win, target, preferred + 1) - 1) end

  local view = vim.fn.winsaveview()
  view.topline = math.max(1, math.min(math.max(1, last - vim.api.nvim_win_get_height(win) + 1),
    view.topline + target - cursor[1]))
  view.lnum, view.col, view.coladd, view.curswant = target, column, 0, preferred
  vim.fn.winrestview(view)
  M.states[win] = { buf = buf, tick = tick, preferred = preferred, cursor = vim.api.nvim_win_get_cursor(win) }
end

local function select_move(move)
  local mode = vim.fn.mode():sub(1, 1)
  local full_rows = mode == 'V' or mode == 'S'
  local block = mode == '\22' or mode == '\19'
  if mode == 's' or mode == 'S' or mode == '\19' then
    vim.cmd.normal({ args = { vim.keycode('<C-g>') }, bang = true })
  elseif mode ~= 'v' and mode ~= 'V' and mode ~= '\22' then
    vim.cmd.normal({ args = { 'v' }, bang = true })
  end
  local anchor = vim.fn.getpos('v')
  move()
  local cursor = vim.api.nvim_win_get_cursor(0)
  if not full_rows and not block and cursor[1] == anchor[2] and cursor[2] == anchor[3] - 1 then
    -- Select mode represents a caret-sized selection as one character. A page
    -- clamped to its anchor must instead remain an empty selection/caret.
    vim.cmd.normal({ args = { vim.keycode('<Esc>') }, bang = true })
    vim.api.nvim_win_set_cursor(0, cursor)
    -- Search inputs are editable scratch buffers, so the file-only shortcut
    -- dispatcher does not restore their Insert mode after an empty selection.
    if vim.bo.modifiable and not vim.bo.readonly
      and (vim.bo.filetype == 'jetvim-search' or vim.bo.filetype == 'jetvim-project-search') then
      vim.cmd.startinsert()
    end
  else
    vim.cmd.normal({ args = { vim.keycode('<C-g>') }, bang = true })
  end
end

function M.select(direction)
  select_move(function() M.move(direction) end)
end

function M.select_line_boundary(ending)
  select_move(function()
    local row = vim.api.nvim_win_get_cursor(0)[1]
    vim.api.nvim_win_set_cursor(0, { row, ending and #vim.api.nvim_get_current_line() or 0 })
  end)
end

vim.api.nvim_create_autocmd('WinClosed', { callback = function(event) M.states[tonumber(event.match)] = nil end })
vim.api.nvim_create_autocmd('BufWipeout', { callback = function(event)
  for win, state in pairs(M.states) do if state.buf == event.buf then M.states[win] = nil end end
end })
return M
