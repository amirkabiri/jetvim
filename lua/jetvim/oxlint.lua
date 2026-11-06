-- Oxlint JSON uses one-based UTF-8 byte columns, unlike ESLint's UTF-16.
local M = {}
local function canonical(path)
  return vim.uv.fs_realpath(path) or vim.fs.normalize(path)
end
local function matches(filename, context)
  if type(filename) ~= 'string' or filename == '' then return false end
  if not context or not context.file then return true end
  local path = filename:sub(1, 1) == '/' and filename or (context.cwd or vim.fs.dirname(context.file)) .. '/' .. filename
  return canonical(path) == canonical(context.file)
end
function M.parse(output, _, context)
  local decoded = vim.json.decode(output)
  assert(type(decoded) == 'table' and type(decoded.diagnostics) == 'table' and vim.islist(decoded.diagnostics), 'Expected Oxlint diagnostics JSON')
  local result = {}
  for _, item in ipairs(decoded.diagnostics) do
    assert(type(item) == 'table', 'Invalid Oxlint diagnostic')
    if matches(item.filename, context) then
      local span
      for _, label in ipairs(item.labels or {}) do
        if type(label) == 'table' and type(label.span) == 'table' then
          if not span or label.primary or label.isPrimary then span = label.span end
          if label.primary or label.isPrimary then break end
        end
      end
      if span then
        local severity = ({ error = 'error', warning = 'warn', advice = 'info', info = 'info', help = 'hint' })[item.severity]
        assert(severity, 'Invalid Oxlint diagnostic severity')
        assert(type(span.line) == 'number' and span.line >= 1 and span.line % 1 == 0, 'Invalid Oxlint diagnostic line')
        assert(type(span.column) == 'number' and span.column >= 1 and span.column % 1 == 0, 'Invalid Oxlint diagnostic column')
        result[#result + 1] = { line = span.line, column = span.column, message = item.message, code = item.code, severity = severity }
      end
    end
  end
  return result
end
return M
