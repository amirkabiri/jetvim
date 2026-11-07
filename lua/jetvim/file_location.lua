-- File pickers may accept pasted path:line[:column] references as well as names.
local M = {}
local function unquote(value)
  local first = value:sub(1, 1)
  if #value >= 2 and (first == '"' or first == "'") and value:sub(-1) == first then
    return value:sub(2, -2)
  end
  return value
end
function M.new(files)
  local known = {}
  for _, path in ipairs(files) do known[path] = true end
  local root = require('jetvim.project').root
  local function relative(path)
    path = path:gsub('^%./', '')
    if root == '/' then path = path:gsub('^/', '')
    elseif path:sub(1, #root + 1) == root .. '/' then path = path:sub(#root + 2) end
    return path
  end
  local function parse(raw)
    raw = raw or ''
    -- A real filename takes precedence over a numeric suffix. Quoting just the
    -- pathname ("name:12":4) can disambiguate a colon-bearing file and location.
    if known[relative(raw)] then return { query = relative(raw) } end
    local value = unquote(vim.trim(raw))
    if known[relative(value)] then return { query = relative(value) } end
    local path, line = value:match('^(.+):(%d+)$')
    if path then
      path = relative(unquote(vim.trim(path)))
      if known[path] then return { query = path, line = math.max(1, tonumber(line)) } end
    end
    local prefix, row, col = value:match('^(.+):(%d+):(%d+)$')
    if prefix then
      return { query = relative(unquote(vim.trim(prefix))), line = math.max(1, tonumber(row)), col = math.max(1, tonumber(col)) }
    end
    if path then return { query = path, line = math.max(1, tonumber(line)) } end
    return { query = relative(value) }
  end
  return {
    query = function(raw) return parse(raw).query end,
    open = function(path, raw)
      local location = parse(raw)
      require('jetvim.project').open(path, location.line, location.col and location.col - 1)
    end,
  }
end
return M
