local M = {}
local palette = {
  editor = '#1e1f22', panel = '#1b1c1e', bar = '#2b2d30', popup = '#25262a',
  text = '#bcbec4', bright = '#dfe1e5', muted = '#868a91', border = '#323438',
  blue = '#6c95eb', selected = '#2d4268', tab = '#25324d',
  purple = '#c191d6', green = '#6aab73', orange = '#cf8e6d', red = '#e06c75',
}
M.palette = palette
local file_groups = {
  modified = 'JetvimFileModified', untracked = 'JetvimFileUntracked', added = 'JetvimFileAdded',
  conflict = 'JetvimFileConflict', deleted = 'JetvimFileDeleted',
}
function M.filename_group(status) return file_groups[status] or 'JetvimFileNormal' end
local function safe(text) return tostring(text):gsub('%%', '%%%%') end
local function display(text) return text:gsub('\r', '␍'):gsub('\n', '↵'):gsub('\t', '⇥') end
local function truncate(text, width)
  if vim.fn.strdisplaywidth(text) <= width then return text end
  local result = ''
  for char in text:gmatch('[%z\1-\127\194-\244][\128-\191]*') do
    if vim.fn.strdisplaywidth(result .. char .. '…') > width then break end
    result = result .. char
  end
  return result .. '…'
end
function M.remember_editor()
  if vim.bo.buftype == '' and vim.bo.buflisted then M.active_editor = vim.api.nvim_get_current_buf() end
end
function M.setup(options)
  require('jetvim.icons').setup(options)
  local c = palette
  local highlights = {
    Normal = { fg = c.text, bg = c.editor }, NormalNC = { fg = c.text, bg = c.editor },
    EndOfBuffer = { fg = c.editor, bg = c.editor }, SignColumn = { bg = c.editor },
    ColorColumn = { bg = '#26282e' }, CursorLine = { bg = '#26282e' },
    CursorLineNr = { fg = c.text, bg = '#26282e' }, LineNr = { fg = '#6f737a', bg = c.editor },
    WinSeparator = { fg = c.border, bg = c.editor }, VertSplit = { fg = c.border, bg = c.editor },
    FoldColumn = { fg = c.muted, bg = c.editor }, Folded = { fg = c.muted, bg = '#26282e' },
    Visual = { bg = '#2e436e' }, VisualNOS = { bg = '#33373f' },
    Search = { fg = '#f5d68b', bg = '#5a4a21' }, IncSearch = { fg = c.editor, bg = '#d9bb76' },
    CurSearch = { fg = c.editor, bg = '#d9bb76' },
    NormalFloat = { fg = c.text, bg = c.popup }, FloatBorder = { fg = '#4e5157', bg = c.popup },
    FloatTitle = { fg = c.bright, bg = c.popup, bold = true }, FloatFooter = { fg = c.muted, bg = c.popup },
    Pmenu = { fg = c.text, bg = c.popup }, PmenuSel = { fg = c.bright, bg = c.selected },
    PmenuSbar = { bg = c.bar }, PmenuThumb = { bg = '#555960' },
    StatusLine = { fg = c.muted, bg = c.bar }, StatusLineNC = { fg = c.muted, bg = c.bar },
    TabLineFill = { fg = c.muted, bg = c.panel }, TabLine = { fg = '#a8adb5', bg = c.editor },
    TabLineSel = { fg = c.bright, bg = c.tab, underline = true, sp = c.blue },
    JetvimTabActiveEdge = { fg = c.blue, bg = c.tab },
    JetvimTabEdge = { fg = c.border, bg = c.editor },
    JetvimBrand = { fg = c.bright, bg = c.panel, bold = true },
    JetvimStatus = { fg = c.muted, bg = c.bar }, JetvimStatusMode = { fg = c.text, bg = c.bar },
    JetvimTreeNormal = { fg = c.text, bg = c.panel },
    JetvimTreeCursorLine = { bg = c.selected },
    JetvimTreeCursorLineInactive = { bg = '#35373b' },
    JetvimTreeTitle = { fg = c.bright, bg = c.panel, bold = true },
    JetvimTreeMuted = { fg = c.muted, bg = c.panel },
    JetvimTreeName = { fg = c.text }, JetvimTreeArrow = { fg = c.muted },
    JetvimTreeSearch = { fg = '#f5d68b', bg = '#5a4a21', bold = true },
    JetvimToolNormal = { fg = c.text, bg = c.panel }, JetvimToolCursorLine = { bg = c.selected },
    JetvimToolTitle = { fg = c.bright, bg = c.panel, bold = true },
    JetvimMuted = { fg = c.muted, bg = c.panel }, JetvimSeparator = { fg = c.border, bg = c.editor },
    JetvimGitAdded = { fg = c.green }, JetvimGitChanged = { fg = c.blue }, JetvimGitDeleted = { fg = c.red },
    JetvimGutterAdded = { fg = c.green, bg = c.editor },
    JetvimGutterModified = { fg = c.blue, bg = c.editor },
    JetvimGutterDeleted = { fg = c.red, bg = c.editor },
    JetvimPopup = { fg = c.text, bg = c.popup }, JetvimPopupBorder = { fg = '#4e5157', bg = c.popup },
    JetvimPickerSelected = { fg = c.bright, bg = c.selected },
    Directory = { fg = c.text }, Title = { fg = c.bright, bold = true },
    Comment = { fg = '#7a7e85', italic = true }, String = { fg = c.green },
    Character = { fg = c.green }, Constant = { fg = c.orange }, Number = { fg = c.orange },
    Boolean = { fg = c.orange }, Float = { fg = c.orange }, Identifier = { fg = c.text },
    Function = { fg = '#56a8f5' }, Statement = { fg = c.orange }, Conditional = { fg = c.orange },
    Repeat = { fg = c.orange }, Keyword = { fg = c.orange }, Operator = { fg = c.text },
    Type = { fg = c.text }, Special = { fg = '#d9bb76' }, Delimiter = { fg = c.text },
    PreProc = { fg = c.orange }, Include = { fg = c.orange }, StorageClass = { fg = c.orange },
    Error = { fg = c.red }, ErrorMsg = { fg = c.red }, WarningMsg = { fg = '#d9bb76' },
    DiagnosticError = { fg = c.red }, DiagnosticWarn = { fg = '#d9bb76' },
    DiagnosticInfo = { fg = c.blue }, DiagnosticHint = { fg = c.muted },
    DiagnosticVirtualTextError = { fg = '#b96b74', bg = c.editor },
    DiagnosticVirtualTextWarn = { fg = '#b5a06b', bg = c.editor },
    DiffAdd = { bg = '#283d30' }, DiffDelete = { fg = '#d18a94', bg = '#452b2e' },
    DiffChange = { bg = '#28364a' }, DiffText = { bg = '#354f78' },
    diffAdded = { fg = c.green, bg = '#23372b' }, diffRemoved = { fg = '#d18a94', bg = '#3c282c' },
    diffChanged = { fg = c.blue }, diffFile = { fg = c.muted },
    diffNewFile = { fg = c.green }, diffOldFile = { fg = '#d18a94' },
    diffIndexLine = { fg = c.muted }, diffLine = { fg = c.blue },
    jsonKeyword = { fg = c.purple }, jsonString = { fg = c.green }, jsonNumber = { fg = c.orange },
    jsonBoolean = { fg = c.orange }, jsonNull = { fg = c.orange },
    ['@property'] = { fg = c.purple }, ['@string.special.key'] = { fg = c.purple },
    ['@string'] = { fg = c.green }, ['@number'] = { fg = c.orange }, ['@boolean'] = { fg = c.orange },
    ['@keyword'] = { fg = c.orange }, ['@function'] = { fg = '#56a8f5' },
    ['@variable'] = { fg = c.text }, ['@comment'] = { fg = '#7a7e85', italic = true },
    ['@punctuation.bracket'] = { fg = c.text }, ['@punctuation.delimiter'] = { fg = c.text },
  }
  local filename_colors = {
    Normal = c.text, Modified = c.blue, Untracked = c.red, Added = c.green, Conflict = c.red, Deleted = c.red,
  }
  for name, color in pairs(filename_colors) do
    highlights['JetvimFile' .. name] = { fg = color }
    highlights['JetvimFile' .. name .. 'Tab'] = { fg = color, bg = c.editor }
    highlights['JetvimFile' .. name .. 'Active'] = { fg = color, bg = c.tab, underline = true, sp = c.blue }
  end
  for name, color in pairs(require('jetvim.icons').colors) do
    highlights['JetvimIcon' .. name] = { fg = color }
    highlights['JetvimIcon' .. name .. 'Tab'] = { fg = color, bg = c.editor }
    highlights['JetvimIcon' .. name .. 'Active'] = { fg = color, bg = c.tab, underline = true, sp = c.blue }
  end
  for name, spec in pairs(highlights) do vim.api.nvim_set_hl(0, name, spec) end
  M.remember_editor()
end
function M.status()
  local mode = vim.fn.mode()
  local label = (mode:match('^[vVsS]') or mode == '\22' or mode == '\19') and 'SELECT'
    or (mode:match('^[it]') and 'EDIT' or 'VIM')
  local project = require('jetvim.project').root
  local filetype = vim.bo.filetype ~= '' and vim.bo.filetype:upper() or 'TEXT'
  return '%#JetvimStatus#  ' .. safe(display(vim.fs.basename(project))) .. '  ›  %f %m%r %='
    .. '%#JetvimStatusMode# ' .. label .. ' %#JetvimStatus#  %l:%c  │  '
    .. safe((vim.bo.fileencoding ~= '' and vim.bo.fileencoding or vim.o.encoding):upper())
    .. '  │  ' .. vim.bo.shiftwidth .. ' spaces  │  ' .. safe(filetype) .. '  '
end
function M.tabs()
  local tree = package.loaded['jetvim.tree']
  local left_width = tree and tree.win and vim.api.nvim_win_is_valid(tree.win)
    and vim.api.nvim_win_get_tabpage(tree.win) == vim.api.nvim_get_current_tabpage()
    and vim.api.nvim_win_get_width(tree.win) + 1 or 10
  local brand = left_width == 10 and '  Jetvim' or '  ' .. truncate(display(vim.fs.basename(require('jetvim.project').root)), math.max(1, left_width - 3))
  local parts = { '%#JetvimBrand#' .. safe(brand) .. string.rep(' ', math.max(1, left_width - vim.fn.strdisplaywidth(brand))) }
  local buffers, active = {}, 1
  local current = vim.bo.buftype == '' and vim.api.nvim_get_current_buf() or M.active_editor
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    if vim.bo[buf].buflisted and vim.bo[buf].buftype == '' then
      local path = vim.api.nvim_buf_get_name(buf)
      local name = vim.fs.basename(path)
      name = truncate(name ~= '' and display(name) or 'Untitled', 24)
      local icon = require('jetvim.icons').for_path(path)
      -- Redraws only read the shared cache; they never launch Git themselves.
      local vcs = package.loaded['jetvim.vcs']
      local status = vcs and vcs.status and vcs.status(path) or nil
      local text = ' ' .. icon.text .. ' ' .. name .. (vim.bo[buf].modified and ' ● ' or '   ')
      buffers[#buffers + 1] = { buf = buf, icon = icon, name = name, status = status, width = vim.fn.strdisplaywidth(text) + 1 }
      if buf == current then active = #buffers end
    end
  end
  local first, last, width = active, active, buffers[active] and buffers[active].width or 0
  local available = math.max(1, vim.o.columns - left_width - 3)
  while true do
    if first > 1 and width + buffers[first - 1].width <= available then
      first, width = first - 1, width + buffers[first - 1].width
    elseif last < #buffers and width + buffers[last + 1].width <= available then
      last, width = last + 1, width + buffers[last + 1].width
    else break end
  end
  if first > 1 then parts[#parts + 1] = '%#TabLineFill#‹' end
  for i = first, last do
    local entry = buffers[i]
    if entry then
      local selected = entry.buf == current
      local base = selected and 'TabLineSel' or 'TabLine'
      local edge = selected and 'JetvimTabActiveEdge' or 'JetvimTabEdge'
      parts[#parts + 1] = '%#' .. edge .. '#' .. (selected and '▎' or '│')
        .. '%#' .. base .. '# '
      parts[#parts + 1] = '%#' .. entry.icon.hl .. (selected and 'Active' or 'Tab') .. '#' .. safe(entry.icon.text)
        .. '%#' .. base .. '# '
        .. '%#' .. M.filename_group(entry.status) .. (selected and 'Active' or 'Tab') .. '#' .. safe(entry.name)
        .. '%#' .. base .. '#' .. (vim.bo[entry.buf].modified and ' ● ' or '   ')
    end
  end
  if last < #buffers then parts[#parts + 1] = '%#TabLineFill#›' end
  return table.concat(parts) .. '%#TabLineFill#%='
end
return M
