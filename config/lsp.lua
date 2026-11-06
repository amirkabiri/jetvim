-- Optional language intelligence. No servers are downloaded or started by default.
-- Enable a server you already have by uncommenting its block, then restart Jetvim.
-- All Jetvim shortcuts work in insert, selection, and Vim normal mode.
-- Definition, completion, refactoring, symbols and formatting need server support.

-- Go:
vim.lsp.config('gopls', {
  cmd = { 'gopls' }, filetypes = { 'go', 'gomod', 'gowork' },
  root_markers = { 'go.work', 'go.mod', '.git' },
})
vim.lsp.enable('gopls')

-- Python (python-lsp-server):
-- vim.lsp.config('pylsp', {
--   cmd = { 'pylsp' }, filetypes = { 'python' },
--   root_markers = { 'pyproject.toml', 'setup.py', '.git' },
-- })
-- vim.lsp.enable('pylsp')

-- TypeScript / JavaScript:
vim.lsp.config('ts_ls', {
  cmd = { 'typescript-language-server', '--stdio' },
  filetypes = { 'javascript', 'javascriptreact', 'typescript', 'typescriptreact' },
  root_markers = { 'tsconfig.json', 'package.json', '.git' },
})
vim.lsp.enable('ts_ls')
