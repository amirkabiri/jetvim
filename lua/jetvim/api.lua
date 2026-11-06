-- Settings extensions use one-based UTF-8 byte positions, like editor status.
local M = { namespaces = {} }
local function namespace(source)
  assert(type(source) == 'string' and source ~= '', 'A diagnostic/annotation source is required')
  M.namespaces[source] = M.namespaces[source] or vim.api.nvim_create_namespace('JetvimExtension:' .. source)
  return M.namespaces[source]
end
local function buffer(buf) return (buf == nil or buf == 0) and vim.api.nvim_get_current_buf() or buf end
function M.diagnostics(source, buf, entries)
  buf = buffer(buf)
  if not vim.api.nvim_buf_is_valid(buf) then return end
  assert(type(entries or {}) == 'table' and vim.islist(entries or {}), 'Diagnostics must be a list')
  local result, count = {}, vim.api.nvim_buf_line_count(buf)
  for _, entry in ipairs(entries or {}) do
    assert(type(entry) == 'table', 'Each diagnostic must be a table')
    local line, column = entry.line or 1, entry.column or 1
    assert(type(line) == 'number' and line >= 1 and line % 1 == 0, 'Diagnostic line must be a positive integer')
    assert(type(column) == 'number' and column >= 1 and column % 1 == 0, 'Diagnostic column must be a positive integer')
    local row = math.max(0, math.min(count - 1, line - 1))
    local text = vim.api.nvim_buf_get_lines(buf, row, row + 1, false)[1] or ''
    local severity = entry.severity or 'error'
    if type(severity) == 'string' then severity = vim.diagnostic.severity[severity:upper()] end
    assert(type(severity) == 'number' and severity >= 1 and severity <= 4 and severity % 1 == 0, 'Invalid diagnostic severity')
    result[#result + 1] = { lnum = row, col = math.max(0, math.min(#text, column - 1)),
      message = tostring(entry.message or ''), severity = severity or vim.diagnostic.severity.ERROR,
      source = source, code = entry.code }
  end
  vim.diagnostic.set(namespace(source), buf, result)
end
function M.annotations(source, buf, entries)
  buf = buffer(buf)
  if not vim.api.nvim_buf_is_valid(buf) then return end
  local ns = namespace('annotations:' .. source)
  vim.api.nvim_buf_clear_namespace(buf, ns, 0, -1)
  vim.api.nvim_set_hl(0, 'JetvimAnnotation', { fg = '#6f737a', default = true })
  for _, entry in ipairs(entries or {}) do
    local row = (tonumber(entry.line) or 1) - 1
    if row >= 0 and row < vim.api.nvim_buf_line_count(buf) then
      vim.api.nvim_buf_set_extmark(buf, ns, row, 0, { virt_text = { { tostring(entry.text or ''):gsub('[\r\n]', ' '), entry.highlight or 'JetvimAnnotation' } }, virt_text_pos = 'eol' })
    end
  end
end
return M
