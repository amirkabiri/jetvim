local M = {}
local project = require('jetvim.project')
local ui = require('jetvim.ui')
local edit = require('jetvim.edit')
local function normal(keys)
  vim.cmd.stopinsert()
  vim.cmd.normal({ args = { vim.keycode(keys) }, bang = true })
end
local function lsp(method, callback)
  if #vim.lsp.get_clients({ bufnr = 0, method = method }) == 0 then
    vim.notify('This action needs a language server. Run :JetvimLspInfo for client and installation details.', vim.log.levels.WARN)
    return
  end
  callback()
end
function M.files() ui.pick('Go to File', project.files(), function(path) project.open(path) end) end
function M.palette()
  local items = {}
  for _, binding in ipairs(require('jetvim.keymap').bindings) do
    if M[binding.id] then items[#items + 1] = { label = binding.label .. '  ' .. binding.shortcut, id = binding.id } end
  end
  ui.pick('Find Action', items, function(item) M[item.id]() end)
end
function M.everywhere()
  local items = {}
  for _, path in ipairs(project.files()) do items[#items + 1] = { label = 'File    ' .. path, path = path } end
  for _, binding in ipairs(require('jetvim.keymap').bindings) do
    items[#items + 1] = { label = 'Action  ' .. binding.label, action = binding.id }
  end
  ui.pick('Search Everywhere · files and actions', items, function(item)
    if item.path then project.open(item.path) else M[item.action]() end
  end)
end
function M.recent()
  local items = {}
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    local path = vim.api.nvim_buf_get_name(buf)
    if vim.bo[buf].buflisted and path ~= '' and project.resolve(path) then
      items[#items + 1] = { label = vim.fn.fnamemodify(path, ':.'), buf = buf, used = vim.fn.getbufinfo(buf)[1].lastused }
    end
  end
  table.sort(items, function(a, b) return a.used > b.used end)
  ui.pick('Recent Files', items, function(item)
    require('jetvim.tree').editor(); vim.api.nvim_set_current_buf(item.buf); vim.cmd.startinsert()
  end)
end
function M.locations()
  local items = {}
  local jumps = vim.fn.getjumplist()[1]
  for i = #jumps, 1, -1 do
    local jump = jumps[i]
    local path = vim.api.nvim_buf_get_name(jump.bufnr)
    if path ~= '' and project.resolve(path) then
      items[#items + 1] = { label = vim.fn.fnamemodify(path, ':.') .. ':' .. jump.lnum, path = path, line = jump.lnum, col = jump.col }
    end
  end
  ui.pick('Recent Locations', items, function(item) project.open(item.path, item.line, item.col) end)
end
function M.find()
  ui.input('Find literal text', function(query)
    vim.fn.setreg('/', [[\V]] .. query:gsub(string.char(92), string.char(92, 92)))
    vim.o.hlsearch = true
    vim.fn.search(vim.fn.getreg('/'), 'w')
  end)
end
function M.find_project()
  if vim.fn.executable('rg') ~= 1 then vim.notify('Find in Files requires ripgrep (rg)', vim.log.levels.WARN); return end
  ui.input('Find in Files (literal)', function(query)
    vim.system({ 'rg', '--json', '--fixed-strings', '--hidden', '--max-count', '100',
      '-g', '!.git', '-g', '!.jetvim', '-g', '!node_modules', '--', query, '.' },
      { cwd = project.root, text = true, timeout = 10000 }, function(result)
        vim.schedule(function()
          if result.code ~= 0 and result.code ~= 1 then
            vim.notify('Search failed: ' .. (result.stderr or 'timeout'), vim.log.levels.ERROR); return
          end
          local items = {}
          for line in (result.stdout or ''):gmatch('[^\n]+') do
            local ok, entry = pcall(vim.json.decode, line)
            if ok and entry.type == 'match' and #items < 2000 then
              local data = entry.data
              if data.path.text and data.lines.text then
                items[#items + 1] = { label = data.path.text .. ':' .. data.line_number .. '  ' .. vim.trim(data.lines.text),
                  path = data.path.text, line = data.line_number, col = data.submatches[1].start }
              end
            end
          end
          ui.pick('Find in Files · up to 2000 matches', items, function(item) project.open(item.path, item.line, item.col) end)
        end)
      end)
  end)
end
function M.line()
  ui.input('Go to line[:column]', function(value)
    local row, col = value:match('^(%d+):?(%d*)$')
    if not row then vim.notify('Enter a line number or line:column', vim.log.levels.WARN); return end
    row = math.max(1, math.min(tonumber(row), vim.api.nvim_buf_line_count(0)))
    local text = vim.api.nvim_buf_get_lines(0, row - 1, row, false)[1]
    vim.api.nvim_win_set_cursor(0, { row, math.min(#text, math.max(0, (tonumber(col) or 1) - 1)) })
  end)
end
local function symbols(workspace, classes_only)
  local method = workspace and 'workspace/symbol' or 'textDocument/documentSymbol'
  lsp(method, function()
    if workspace then
      ui.input(classes_only and 'Go to Class' or 'Go to Symbol', function(query)
        local params = { query = query }
        vim.lsp.buf_request(0, method, params, function(err, result, ctx)
          vim.schedule(function()
            if err then vim.notify(err.message, vim.log.levels.ERROR); return end
            local items = {}
            for _, symbol in ipairs(result or {}) do
              if symbol.location and symbol.location.range and (not classes_only or symbol.kind == 5 or symbol.kind == 11 or symbol.kind == 10 or symbol.kind == 23) then
                items[#items + 1] = { label = symbol.name .. '  ' .. (symbol.containerName or ''), location = symbol.location, client = ctx.client_id }
              end
            end
            ui.pick(classes_only and 'Go to Class' or 'Go to Symbol', items, function(item)
              local path = vim.uri_to_fname(item.location.uri)
              if not project.resolve(path) then vim.notify('Symbol is outside this workspace', vim.log.levels.WARN); return end
              local client = vim.lsp.get_client_by_id(item.client)
              vim.lsp.util.show_document(item.location, client and client.offset_encoding or 'utf-16', { focus = true })
            end)
          end)
        end)
      end)
    else vim.lsp.buf.document_symbol() end
  end)
end
function M.classes() symbols(true, true) end
function M.symbols() symbols(true, false) end
function M.structure() symbols(false) end
local methods = {
  definition = { 'textDocument/definition', vim.lsp.buf.definition },
  implementation = { 'textDocument/implementation', vim.lsp.buf.implementation },
  type_definition = { 'textDocument/typeDefinition', vim.lsp.buf.type_definition },
  references = { 'textDocument/references', vim.lsp.buf.references },
  documentation = { 'textDocument/hover', vim.lsp.buf.hover },
  parameters = { 'textDocument/signatureHelp', vim.lsp.buf.signature_help },
  rename = { 'textDocument/rename', vim.lsp.buf.rename },
  intentions = { 'textDocument/codeAction', vim.lsp.buf.code_action },
  format = { 'textDocument/formatting', function() vim.lsp.buf.format({ async = true }) end },
  call_hierarchy = { 'textDocument/prepareCallHierarchy', vim.lsp.buf.incoming_calls },
}
for id, method in pairs(methods) do M[id] = function() lsp(method[1], method[2]) end end
function M.imports()
  lsp('textDocument/codeAction', function()
    vim.lsp.buf.code_action({ context = { only = { 'source.organizeImports' }, diagnostics = {} }, apply = true })
  end)
end
function M.completion()
  lsp('textDocument/completion', function()
    vim.cmd.startinsert()
    vim.api.nvim_feedkeys(vim.keycode('<C-x><C-o>'), 'n', false)
  end)
end
function M.save() vim.cmd.wall() end
function M.close() vim.cmd('confirm bdelete') end
function M.undo() vim.cmd.undo() end
function M.redo() vim.cmd.redo() end
function M.back() normal('<C-o>') end
function M.forward() normal('<C-i>') end
function M.last_edit() normal('g;') end
function M.next_match() normal('n') end
function M.previous_match() normal('N') end
local function cycle_editor(direction)
  local tree = require('jetvim.tree')
  if vim.bo.buftype ~= '' then tree.editor() end
  local current, buffers = vim.api.nvim_get_current_buf(), {}
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    if vim.bo[buf].buflisted and vim.bo[buf].buftype == '' then buffers[#buffers + 1] = buf end
  end
  if #buffers == 0 then return end
  local index = 1
  for i, buf in ipairs(buffers) do if buf == current then index = i; break end end
  vim.api.nvim_set_current_buf(buffers[(index - 1 + direction) % #buffers + 1])
end
function M.next_tab() cycle_editor(1) end
function M.previous_tab() cycle_editor(-1) end
function M.page_up() require('jetvim.paging').move(-1) end
function M.page_down() require('jetvim.paging').move(1) end
function M.next_error() vim.diagnostic.jump({ count = 1, float = true }) end
function M.previous_error() vim.diagnostic.jump({ count = -1, float = true }) end
function M.error_info() vim.diagnostic.open_float() end
function M.fold_open() normal('zo') end
function M.fold_close() normal('zc') end
function M.fold_open_all() normal('zR') end
function M.fold_close_all() normal('zM') end
function M.block_start() normal('[{') end
function M.block_end() normal(']}') end
local function word_position(direction)
  local row, col = unpack(vim.api.nvim_win_get_cursor(0))
  local line = vim.api.nvim_get_current_line()
  if direction == 1 then
    local match = vim.fn.matchstrpos(line, [[\k\+]], col)
    if match[2] >= 0 then return { row, match[3] } end
    if row < vim.api.nvim_buf_line_count(0) then return { row + 1, 0 } end
    return { row, #line }
  end
  if col == 0 and row > 1 then
    return { row - 1, #(vim.api.nvim_buf_get_lines(0, row - 2, row - 1, false)[1]) }
  end
  local prefix, offset, target = line:sub(1, col), 0, 0
  while offset < #prefix do
    local match = vim.fn.matchstrpos(prefix, [[\k\+]], offset)
    if match[2] < 0 then break end
    target, offset = match[2], match[3]
  end
  return { row, target }
end
function M.word_left() vim.api.nvim_win_set_cursor(0, word_position(-1)) end
function M.word_right() vim.api.nvim_win_set_cursor(0, word_position(1)) end
function M.line_start() normal('0') end
function M.line_end() vim.api.nvim_win_set_cursor(0, { vim.api.nvim_win_get_cursor(0)[1], #vim.api.nvim_get_current_line() }) end
function M.file_start() normal('gg') end
function M.file_end()
  local row = vim.api.nvim_buf_line_count(0)
  vim.api.nvim_win_set_cursor(0, { row, #(vim.api.nvim_buf_get_lines(0, row - 1, row, false)[1]) })
end
local function select_motion(motion)
  vim.cmd.stopinsert()
  local mode = vim.fn.mode():sub(1, 1)
  if mode == 's' or mode == 'S' then
    normal('<C-g>')
  elseif mode ~= 'v' and mode ~= 'V' then
    normal('v')
  end
  if type(motion) == 'table' then vim.api.nvim_win_set_cursor(0, motion)
  else normal(motion) end
  normal('<C-g>')
end
function M.select_word_left() select_motion(word_position(-1)) end
function M.select_word_right() select_motion(word_position(1)) end
function M.select_line_start() select_motion('0') end
function M.select_line_end() select_motion({ vim.api.nvim_win_get_cursor(0)[1], #vim.api.nvim_get_current_line() }) end
function M.select_file_start() select_motion('gg') end
function M.select_file_end()
  local row = vim.api.nvim_buf_line_count(0)
  select_motion({ row, #(vim.api.nvim_buf_get_lines(0, row - 1, row, false)[1]) })
end
function M.delete_word_left()
  local row, col = unpack(vim.api.nvim_win_get_cursor(0))
  local target = word_position(-1)
  vim.api.nvim_buf_set_text(0, target[1] - 1, target[2], row - 1, col, {})
  vim.api.nvim_win_set_cursor(0, target)
end
function M.delete_word_right()
  local row, col = unpack(vim.api.nvim_win_get_cursor(0))
  local target = word_position(1)
  vim.api.nvim_buf_set_text(0, row - 1, col, target[1] - 1, target[2], {})
end
function M.join() normal('J') end
function M.split() edit.newline(true) end
function M.newline() edit.newline(false) end
function M.duplicate() edit.duplicate() end
function M.delete_line() edit.delete_line() end
function M.move_up() edit.move_line(-1) end
function M.move_down() edit.move_line(1) end
function M.comment() edit.comment() end
function M.copy() edit.copy(false) end
function M.cut() edit.copy(true) end
function M.paste() edit.paste() end
function M.select_all() edit.select_all() end
function M.extend_selection() edit.extend_selection() end
function M.shrink_selection() edit.shrink_selection() end
function M.indent() edit.indent(1) end
function M.unindent() edit.indent(-1) end
function M.replace() edit.replace() end
function M.paste_history()
  local items = {}
  for _, entry in ipairs(edit.history) do
    items[#items + 1] = { label = table.concat(entry.text, ' ↵ '), entry = entry }
  end
  ui.pick('Paste from History', items, function(item) edit.paste(item.entry.text, item.entry.kind) end)
end
function M.tree() require('jetvim.tree').focus() end
function M.git_changes() require('jetvim.git').toggle() end
function M.reveal() require('jetvim.tree').reveal() end
function M.hide_tools() require('jetvim.tree').hide() end
function M.editor()
  local tree = require('jetvim.tree')
  if vim.bo.filetype == 'jetvim-tree' then tree.open_entry()
  else tree.editor(); vim.cmd.startinsert() end
end
function M.terminal()
  if M.term_win and vim.api.nvim_win_is_valid(M.term_win) then vim.api.nvim_win_close(M.term_win, true); return end
  vim.cmd('botright 12split')
  M.term_win = vim.api.nvim_get_current_win()
  if M.term_buf and vim.api.nvim_buf_is_valid(M.term_buf) then vim.api.nvim_win_set_buf(0, M.term_buf)
  else vim.cmd.enew(); vim.cmd.terminal(); M.term_buf = vim.api.nvim_get_current_buf() end
  vim.cmd.startinsert()
end
function M.help() project.open_tool('docs/shortcuts.md') end
function M.settings() project.open_tool('config/lsp.lua') end
function M.vim_mode() vim.cmd.stopinsert() end
return M
