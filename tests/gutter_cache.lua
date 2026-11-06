local gutter = require('jetvim.gutter')
local checks = 0
local function equal(actual, expected, label)
  assert(vim.deep_equal(actual, expected), label .. ': ' .. vim.inspect(actual) .. ' != ' .. vim.inspect(expected))
  checks = checks + 1
end
local function count(marks, kind)
  local result = 0
  for _, mark in ipairs(marks) do if mark.kind == kind then result = result + 1 end end
  return result
end
local saved_system, saved_executable = vim.system, vim.fn.executable
local queue, calls, kills = {}, {}, 0
local ok, err = pcall(function()
  equal(gutter.compute('one\ntwo\n', 'one\ntwo\n', 2), {}, 'unchanged text')
  equal(gutter.compute('one\ntwo\n', 'one\nchanged\n', 2), { { row = 2, kind = 'modified' } }, 'blue replacement')
  equal(gutter.compute('one\n', 'one\nnew\n', 2), { { row = 2, kind = 'added' } }, 'green addition')
  equal(gutter.compute('one\ntwo\n', 'one\n', 1), { { row = 1, kind = 'deleted' } }, 'EOF deletion clamps to last row')
  equal(gutter.compute('one\ntwo\n', 'two\n', 1), { { row = 1, kind = 'deleted' } }, 'top deletion clamps to first row')
  equal(gutter.compute('one\n', '', 1), { { row = 1, kind = 'deleted' } }, 'whole-file deletion')
  equal(gutter.compute('', 'one\ntwo\n', 2), { { row = 1, kind = 'added' }, { row = 2, kind = 'added' } }, 'untracked file lines')
  local replaced = gutter.compute('one\ntwo\nthree\n', 'changed\n', 1)
  equal(count(replaced, 'modified'), 1, 'replacement has modified mark')
  equal(count(replaced, 'deleted'), 1, 'replacement also records removed lines')
  local extended = gutter.compute('one\n', 'changed\nextra\n', 2)
  equal(count(extended, 'modified'), 1, 'replacement extra modified line')
  equal(count(extended, 'added'), 1, 'replacement extra green line')
  equal(gutter.compute('a\0b', 'a', 1), {}, 'binary baseline skipped')
  equal(gutter.compute('a', 'a\0b', 1), {}, 'binary current text skipped')
  local old_max = gutter.max_bytes
  gutter.max_bytes = 3
  equal(gutter.compute('large', 'a', 1), {}, 'oversized diff skipped')
  gutter.max_bytes = old_max
  equal(vim.o.signcolumn, 'yes:3', 'fixed left slots permit deletion + modification + diagnostic')
  equal(vim.api.nvim_get_hl(0, { name = 'JetvimGutterModified', link = false }).fg, 0x6c95eb, 'modified blue')
  equal(vim.api.nvim_get_hl(0, { name = 'JetvimGutterAdded', link = false }).fg, 0x6aab73, 'added green')
  equal(vim.api.nvim_get_hl(0, { name = 'JetvimGutterDeleted', link = false }).fg, 0xe06c75, 'deleted red')
  vim.system = function(argv, options, callback)
    calls[#calls + 1] = argv
    queue[#queue + 1] = callback
    equal(options.text, false, 'Git byte output')
    return { kill = function() kills = kills + 1 end }
  end
  vim.fn.executable = function(name) if name == 'git' then return 1 end; return saved_executable(name) end
  vim.cmd.enew()
  local buf = vim.api.nvim_get_current_buf()
  vim.api.nvim_buf_set_name(buf, vim.env.JETVIM_ROOT .. '/.jetvim/gutter-mock.lua')
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, { 'changed' })
  gutter.refresh(buf)
  vim.wait(160)
  equal(#calls, 0, 'disabled flag prevents any Git process')
  vim.api.nvim_clear_autocmds({ group = 'JetvimVcs' })
  vim.env.JETVIM_DISABLE_VCS = nil
  local path = vim.api.nvim_buf_get_name(buf)
  local function respond(result)
    local callback = table.remove(queue, 1)
    assert(callback, 'expected a queued subprocess')
    callback(result)
    vim.wait(5)
  end
  gutter.refresh(buf); gutter.refresh(buf); gutter.refresh(buf)
  vim.wait(180)
  equal(#calls, 1, 'refresh bursts coalesce')
  equal(calls[1][1], 'git', 'Git executable')
  equal(vim.tbl_contains(calls[1], '--no-optional-locks'), true, 'no index locks')
  equal(vim.tbl_contains(calls[1], '--literal-pathspecs'), true, 'literal pathspecs')
  equal(vim.tbl_contains(calls[1], 'core.fsmonitor=false'), true, 'no fsmonitor helper')
  respond({ code = 0, stdout = vim.env.JETVIM_ROOT .. '\n' })
  equal(vim.tbl_contains(calls[2], 'check-ignore'), true, 'ignored files checked')
  equal(vim.tbl_contains(calls[2], '--literal-pathspecs'), false, 'check-ignore cannot accept literal pathspec magic')
  equal(calls[2][#calls[2]], './.jetvim/gutter-mock.lua', 'check-ignore filename is safely prefixed')
  respond({ code = 1, stdout = '' })
  equal(vim.tbl_contains(calls[3], 'cat-file'), true, 'baseline uses raw HEAD blob')
  equal(calls[3][#calls[3]], 'HEAD:.jetvim/gutter-mock.lua', 'object path preserved')
  respond({ code = 0, stdout = 'one\ntwo\nthree\n' })
  local marks = vim.api.nvim_buf_get_extmarks(buf, gutter.namespace, 0, -1, { details = true })
  equal(#marks, 2, 'modified/deleted extmarks installed')
  equal(marks[1][4].sign_hl_group, 'JetvimGutterModified', 'left modified sign group')
  equal(marks[2][4].sign_hl_group, 'JetvimGutterDeleted', 'left deleted sign group')
  equal(marks[1][4].virt_text, nil, 'not an inline/right annotation')
  local diagnostic = vim.api.nvim_create_namespace('JetvimGutterTestDiagnostic')
  vim.api.nvim_buf_set_extmark(buf, diagnostic, 0, 0, { sign_text = 'E', sign_hl_group = 'DiagnosticError', priority = 10 })
  local screen = vim.api.nvim_eval_statusline('%s', { winid = vim.api.nvim_get_current_win(), use_statuscol_lnum = 1, highlights = true })
  equal(screen.str:find('E', 1, true) ~= nil, true, 'diagnostic sign remains in left status column')
  equal(screen.str:find('▎', 1, true) ~= nil, true, 'modified sign remains beside diagnostic')
  equal(screen.str:find('▸', 1, true) ~= nil, true, 'deletion sign remains beside diagnostic')
  local before = #calls
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, { 'one', 'two', 'three' })
  gutter.changed(buf); vim.wait(120)
  equal(#calls, before, 'ordinary edit diffs cached HEAD without Git')
  equal(vim.api.nvim_buf_get_extmarks(buf, gutter.namespace, 0, -1, {}), {}, 'reverting clears signs')
  gutter.refresh(buf); vim.wait(160)
  local stale = table.remove(queue, 1)
  gutter.refresh(buf)
  equal(kills > 0, true, 'new refresh cancels old job')
  stale({ code = 0, stdout = vim.env.JETVIM_ROOT .. '\n' }); vim.wait(10)
  equal(#queue, 0, 'cancelled result cannot queue next command')
  vim.wait(160)
  respond({ code = 0, stdout = vim.env.JETVIM_ROOT .. '\n' })
  respond({ code = 0, stdout = '' })
  equal(vim.api.nvim_buf_get_extmarks(buf, gutter.namespace, 0, -1, {}), {}, 'ignored file has no marks')
  gutter.refresh(buf); vim.wait(160)
  respond({ code = 128, stdout = '' })
  equal(vim.api.nvim_buf_get_extmarks(buf, gutter.namespace, 0, -1, {}), {}, 'non-repository clears signs')
  gutter.refresh(buf); vim.wait(160)
  local wiped = table.remove(queue, 1)
  vim.api.nvim_buf_delete(buf, { force = true })
  wiped({ code = 0, stdout = vim.env.JETVIM_ROOT .. '\n' }); vim.wait(10)
  equal(gutter.states[buf], nil, 'wiped buffer drops state and ignores callback')
end)
vim.env.JETVIM_DISABLE_VCS = '1'
vim.system, vim.fn.executable = saved_system, saved_executable
if not ok then vim.api.nvim_err_writeln(err); vim.cmd.cquit() end
print('PASS: ' .. checks .. ' Git gutter pure/cache/sign checks (mocked process API, no Git execution)')
