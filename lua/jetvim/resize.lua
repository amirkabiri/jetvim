local M = {}
local horizontal_step, vertical_step = 4, 2

local function overlaps(a, length_a, b, length_b)
  return math.min(a + length_a, b + length_b) > math.max(a, b)
end

local function neighbors(win, horizontal)
  local position = vim.api.nvim_win_get_position(win)
  local size = horizontal and vim.api.nvim_win_get_width(win) or vim.api.nvim_win_get_height(win)
  local cross_size = horizontal and vim.api.nvim_win_get_height(win) or vim.api.nvim_win_get_width(win)
  local axis, cross = horizontal and 2 or 1, horizontal and 1 or 2
  local before, after = {}, {}
  for _, other in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
    if other ~= win and vim.api.nvim_win_get_config(other).relative == '' then
      local other_position = vim.api.nvim_win_get_position(other)
      local other_size = horizontal and vim.api.nvim_win_get_width(other) or vim.api.nvim_win_get_height(other)
      local other_cross_size = horizontal and vim.api.nvim_win_get_height(other) or vim.api.nvim_win_get_width(other)
      if overlaps(position[cross], cross_size, other_position[cross], other_cross_size) then
        local entry = { win = other, size = other_size }
        if other_position[axis] + other_size + 1 == position[axis] then before[#before + 1] = entry end
        if position[axis] + size + 1 == other_position[axis] then after[#after + 1] = entry end
      end
    end
  end
  return before, after, size
end

function M.move(direction)
  local horizontal = direction == 'left' or direction == 'right'
  assert(horizontal or direction == 'up' or direction == 'down', 'Unknown resize direction')
  local win = vim.api.nvim_get_current_win()
  if vim.api.nvim_win_get_config(win).relative ~= '' then return end
  local before, after, size = neighbors(win, horizontal)
  local toward_before = direction == 'left' or direction == 'up'
  local adjacent = toward_before and before or after
  local growing = #adjacent > 0
  if not growing then adjacent = toward_before and after or before end
  if #adjacent == 0 then return end

  local minimum = horizontal and math.max(10, vim.o.winminwidth) or math.max(3, vim.o.winminheight)
  local amount = horizontal and horizontal_step or vertical_step
  if growing then
    for _, neighbor in ipairs(adjacent) do amount = math.min(amount, math.max(0, neighbor.size - minimum)) end
  else amount = math.min(amount, math.max(0, size - minimum)) end
  if amount == 0 then return end

  -- Move the actual shared divider, rather than merely changing a width and
  -- letting Neovim choose which neighboring pane should donate the space.
  local boundary = (#before > 0 and toward_before) or (#after == 0 and not toward_before)
  local owner = boundary and adjacent[1].win or win
  local delta = toward_before and -amount or amount
  if horizontal then vim.fn.win_move_separator(owner, delta)
  else vim.fn.win_move_statusline(owner, delta) end
  -- Capture explicit keyboard movement synchronously, including several keys
  -- delivered in one terminal input batch before WinResized is dispatched.
  local layout = package.loaded['jetvim.layout']
  if layout then layout.capture() end
end

return M
