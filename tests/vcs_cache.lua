-- Pure cache/process-orchestration checks: vim.system is replaced before the
-- disabled provider is enabled, so this suite never starts Git.
local original_system = vim.system
local original_disabled = vim.env.JETVIM_DISABLE_VCS
local project = require('jetvim.project')
local original_root = project.root
local vcs = require('jetvim.vcs')
local calls, checks, killed = {}, 0, 0
local function equal(actual, expected, label)
  assert(vim.deep_equal(actual, expected), label .. ': expected ' .. vim.inspect(expected) .. ', got ' .. vim.inspect(actual))
  checks = checks + 1
end
local function wait_for(predicate, label)
  assert(vim.wait(1000, predicate, 10), label)
  checks = checks + 1
end
local ok, err = xpcall(function()
  vim.system = function(argv, options, callback)
    calls[#calls + 1] = { argv = argv, options = options, callback = callback }
    return { kill = function(_, signal) if signal == 15 then killed = killed + 1 end end }
  end
  vcs.refresh()
  vim.wait(180)
  equal(#calls, 0, 'disabled provider never invokes process API')
  local root = original_root
  local output = 'MM both.txt\0?? new:[*].txt\0A  added.txt\0 D removed.txt\0UU conflict.txt\0R  renamed.txt\0old.txt\0 M line\r\nname.txt\0!! ignored.txt\0'
  local parsed = vcs.parse_status(output, root, root)
  equal(parsed[root .. '/both.txt'], 'modified', 'staged and unstaged modification stays blue')
  equal(parsed[root .. '/new:[*].txt'], 'untracked', 'untracked filename is literal')
  equal(parsed[root .. '/added.txt'], 'added', 'staged addition')
  equal(parsed[root .. '/removed.txt'], 'deleted', 'deletion')
  equal(parsed[root .. '/conflict.txt'], 'conflict', 'unmerged conflict')
  equal(parsed[root .. '/renamed.txt'], 'modified', 'rename destination')
  equal(parsed[root .. '/old.txt'], nil, 'rename old path is consumed')
  equal(parsed[root .. '/line\r\nname.txt'], 'modified', 'CRLF bytes in filename preserved')
  equal(parsed[root .. '/ignored.txt'], nil, 'ignored entries remain neutral')
  equal(vcs.parse_status(' M ../outside.txt\0', root, root), {}, 'outside lexical paths excluded')

  vim.env.JETVIM_DISABLE_VCS = nil
  vcs.refresh(); vcs.refresh(); vcs.refresh()
  wait_for(function() return #calls == 1 end, 'refresh bursts debounce into one discovery')
  local discovery = calls[1]
  equal(discovery.options.text, false, 'discovery stdout remains byte data')
  local combined = table.concat(discovery.argv, '\n')
  equal(combined:find('--no-pager', 1, true) ~= nil, true, 'pager disabled')
  equal(combined:find('--no-optional-locks', 1, true) ~= nil, true, 'optional locks disabled')
  equal(combined:find('--literal-pathspecs', 1, true) ~= nil, true, 'pathspecs are literal')
  discovery.callback({ code = 0, stdout = root .. '\n', stderr = '' })
  wait_for(function() return #calls == 2 end, 'discovery schedules status query')
  equal(calls[2].options.text, false, 'status stdout remains byte data')
  equal(vim.list_slice(calls[2].argv, #calls[2].argv - 1), { '--', '.' }, 'status scopes literal current project')
  calls[2].callback({ code = 0, stdout = output, stderr = '' })
  wait_for(function() return vcs.status(root .. '/both.txt') == 'modified' end, 'status result populates cache')
  equal(vcs.status(root .. '/new:[*].txt'), 'untracked', 'cache exposes untracked state')
  local count = #calls
  for _ = 1, 1000 do vcs.status(root .. '/both.txt') end
  equal(#calls, count, 'render-time status lookups never invoke process API')

  vcs.refresh()
  wait_for(function() return #calls == count + 1 end, 'next refresh starts fresh discovery')
  local stale = calls[#calls]
  vcs.refresh()
  stale.callback({ code = 0, stdout = root .. '\n', stderr = '' })
  vim.wait(60)
  equal(#calls, count + 1, 'stale discovery result cannot schedule status')
  equal(killed > 0, true, 'superseded process is canceled')

  project.root = root .. '/.jetvim'
  equal(vcs.status(root .. '/both.txt'), nil, 'changed project cannot read old cache')
  vcs.refresh()
  equal(next(vcs._cache), nil, 'project change clears stale statuses immediately')
  vim.env.JETVIM_DISABLE_VCS = '1'
  vcs.refresh()
  local disabled_count = #calls
  vim.wait(180)
  equal(#calls, disabled_count, 'disabling cancels pending refresh without process spawn')
  equal(vcs.status(root .. '/both.txt'), nil, 'disabled provider returns no status')
  print('PASS: ' .. checks .. ' VCS cache checks with mocked process API (no Git execution)')
end, debug.traceback)
vim.env.JETVIM_DISABLE_VCS = '1'
vcs.refresh()
project.root = original_root
vim.system = original_system
vim.env.JETVIM_DISABLE_VCS = original_disabled
if not ok then vim.api.nvim_err_writeln(err); vim.cmd.cquit() end
