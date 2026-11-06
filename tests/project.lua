local ok, err = pcall(function()
  local project = require('jetvim.project')
  assert(project.root == vim.uv.cwd(), 'Project must use selected working directory')
  assert(project.root ~= vim.env.JETVIM_ROOT, 'Fixture should be a separate project')
  assert(vim.fn.expand('%:p') == project.root .. '/example.lua', 'File arguments must be relative to project')
  assert(vim.fn.stdpath('cache'):sub(1, #vim.env.JETVIM_ROOT) == vim.env.JETVIM_ROOT, 'Runtime must stay in installation')
  assert(vim.deep_equal(project.files(), { 'example.lua' }), 'Search must use selected project')
  vim.api.nvim_buf_set_lines(0, 0, -1, false, { '-- project write works' })
  vim.cmd.write()
  require('jetvim.actions').help()
  assert(vim.api.nvim_buf_get_name(0) == vim.env.JETVIM_ROOT .. '/docs/shortcuts.md', 'Help must use installation')
  require('jetvim.actions').settings()
  assert(vim.api.nvim_buf_get_name(0) == vim.env.JETVIM_ROOT .. '/config/lsp.lua', 'Settings must use installation')
  require('jetvim.tree').focus()
  local found = false
  for _, entry in pairs(require('jetvim.tree').rows) do
    assert(entry.root and entry.path == project.root or entry.path:sub(1, #project.root + 1) == project.root .. '/', 'Tree must use project')
    if entry.path == project.root .. '/example.lua' then found = true end
  end
  assert(found, 'Project file must appear in tree')
end)
if not ok then
  vim.api.nvim_err_writeln(tostring(err))
  vim.cmd.cquit()
end
