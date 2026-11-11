local M = {}
local generation = 0
local function point_before(a, b)
  return a.line < b.line or (a.line == b.line and a.character < b.character)
end
local function same_file(uri, name)
  local ok, path = pcall(vim.uri_to_fname, uri)
  if not ok then return false end
  return (vim.uv.fs_realpath(path) or vim.fs.normalize(path)) == name
end
local function location_parts(location)
  return location.targetUri or location.uri,
    location.targetSelectionRange or location.range or location.targetRange
end
-- ElixirLS may return the whole declaration beginning at `def`, where it
-- cannot itself resolve a symbol. Keep that range, but jump to the identifier.
local function elixir_selection(item, range, encoding)
  local text = item.text or ''
  local indent, keyword, identifier, tail = text:match('^(%s*)(def[%a]*)%s+([%a_\128-\255][%w_\128-\255]*[!?]?)(.*)$')
  local declarations = { def = true, defp = true, defmacro = true, defmacrop = true, defguard = true, defguardp = true }
  if not declarations[keyword] or identifier == 'unquote' or item.col ~= #indent + 1 then return end
  tail = tail:gsub('^%s+', '')
  if tail ~= '' and not tail:match('^[%(,]') and not tail:match('^do[%s:]') and tail ~= 'do' then return end
  local first = assert(text:find(identifier, #indent + #keyword + 1, true)) - 1
  local selection = {
    start = { line = range.start.line, character = vim.str_utfindex(text, encoding, first, false) },
    ['end'] = { line = range.start.line, character = vim.str_utfindex(text, encoding, first + #identifier, false) },
  }
  if point_before(range['end'], selection['end']) then return end
  return selection, first + 1
end
function M.definition()
  generation = generation + 1
  local token = generation
  local buf, win = vim.api.nvim_get_current_buf(), vim.api.nvim_get_current_win()
  local cursor, tick = vim.api.nvim_win_get_cursor(win), vim.api.nvim_buf_get_changedtick(buf)
  local original_lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
  local name = vim.api.nvim_buf_get_name(buf)
  name = vim.uv.fs_realpath(name) or vim.fs.normalize(name)
  local function current(check_cursor)
    return token == generation and vim.api.nvim_win_is_valid(win) and vim.api.nvim_buf_is_valid(buf)
      and vim.api.nvim_get_current_win() == win and vim.api.nvim_get_current_buf() == buf
      and (vim.api.nvim_buf_get_changedtick(buf) == tick
        or vim.deep_equal(vim.api.nvim_buf_get_lines(buf, 0, -1, false), original_lines))
      and (check_cursor == false or vim.deep_equal(vim.api.nvim_win_get_cursor(win), cursor))
  end
  local function notify(message)
    if current() then vim.notify(message, vim.log.levels.INFO) end
  end
  local function request(method, complete)
    local clients = vim.lsp.get_clients({ bufnr = buf, method = method })
    if #clients == 0 then notify('This action needs a language server supporting ' .. method); return end
    local left, finished, responses, requests = #clients, false, {}, {}
    local function finish()
      if finished or left > 0 then return end
      finished = true
      if current() then complete(responses) end
    end
    for _, client in ipairs(clients) do
      local params = vim.lsp.util.make_position_params(win, client.offset_encoding)
      if method == 'textDocument/references' then params.context = { includeDeclaration = false } end
      local answered = false
      local function receive(err, result)
        if answered or finished then return end
        answered = true
        responses[#responses + 1] = { error = err, result = result, client = client, position = params.position }
        left = left - 1
        vim.schedule(finish)
      end
      local ok, accepted, id = pcall(client.request, client, method, params, receive, buf)
      if not ok or not accepted then receive({ message = 'Language server request failed' })
      else requests[#requests + 1] = { client = client, id = id } end
    end
    vim.defer_fn(function()
      if finished then return end
      for _, item in ipairs(requests) do pcall(item.client.cancel_request, item.client, item.id) end
      left = 0
      if #responses == 0 then
        finished = true
        notify('Language server request timed out')
        return
      end
      finish()
    end, 10000)
  end
  local function entries(responses, definition)
    local result, seen, errors = {}, {}, {}
    for _, response in ipairs(responses) do
      if response.error then errors[#errors + 1] = response.error.message or 'Language server request failed' end
      local locations = response.result
      if type(locations) == 'table' then
        if locations.uri or locations.targetUri then locations = { locations } end
        for _, location in ipairs(locations) do
          local uri, range = location_parts(location)
          if type(uri) == 'string' and type(range) == 'table' and range.start and range['end'] then
            local normalized = { uri = uri, range = range }
            local ok, items = pcall(vim.lsp.util.locations_to_items, { normalized }, response.client.offset_encoding)
            if ok and items[1] then
              local item = items[1]
              if definition and response.client.name == 'elixirls' then
                local selection, column = elixir_selection(item, range, response.client.offset_encoding)
                if selection then
                  normalized = { targetUri = uri, targetRange = range, targetSelectionRange = selection }
                  range, item.col = selection, column
                end
              end
              local key = item.filename .. ':' .. item.lnum .. ':' .. item.col
              if not seen[key] then
                seen[key] = true
                result[#result + 1] = {
                  label = vim.fn.fnamemodify(item.filename, ':.') .. ':' .. item.lnum .. ':' .. item.col
                    .. '  ' .. (item.text or ''):gsub('^%s+', ''),
                  location = normalized, encoding = response.client.offset_encoding,
                  self = same_file(uri, name) and not point_before(response.position, range.start)
                    and (point_before(response.position, range['end'])
                      or vim.deep_equal(range.start, range['end']) and vim.deep_equal(response.position, range.start)),
                }
              end
            end
          end
        end
      end
    end
    return result, errors
  end
  local function jump(item, from_picker)
    -- The picker restores its origin before invoking this callback. Leaving
    -- Insert mode for its prompt can shift that origin caret one character left;
    -- a deliberate choice still applies if the origin buffer/text is unchanged.
    if not current(not from_picker) then return end
    vim.lsp.util.show_document(item.location, item.encoding, { focus = true })
  end
  local function open_usages(items)
    -- Check the origin once: each deliberate jump changes the active buffer,
    -- so the single-result cursor guard cannot be reapplied to later choices.
    if not current(false) then return end
    local opened = {}
    for _, item in ipairs(items) do
      local path = vim.uri_to_fname(item.location.uri)
      local key = vim.uv.fs_realpath(path) or vim.fs.normalize(path)
      if not opened[key] then
        opened[key] = true
        local ok, shown = pcall(vim.lsp.util.show_document, item.location, item.encoding, { focus = true })
        if ok and shown then
          -- LSP locations can have been preloaded as unlisted buffers. Make
          -- chosen files visible in Jetvim's existing editor tab strip.
          vim.bo[vim.api.nvim_get_current_buf()].buflisted = true
        elseif not ok then
          vim.notify('Cannot open usage: ' .. tostring(shown), vim.log.levels.WARN)
        end
      end
    end
  end
  request('textDocument/definition', function(responses)
    local definitions, errors = entries(responses, true)
    if #definitions == 0 then notify(errors[1] or 'No definition found'); return end
    local at_definition = false
    for _, item in ipairs(definitions) do if item.self then at_definition = true; break end end
    if at_definition then
      request('textDocument/references', function(replies)
        local usages, failures = entries(replies)
        if #usages == 0 then notify(failures[1] or 'No usages found'); return end
        require('jetvim.ui').pick('Usages', usages, function(item) jump(item, true) end,
          { accept_many = open_usages })
      end)
    elseif #definitions == 1 then jump(definitions[1])
    else require('jetvim.ui').pick('Definitions', definitions, function(item) jump(item, true) end) end
  end)
end
return M
