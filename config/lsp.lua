-- Optional language intelligence. Install tools explicitly before enabling them.
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

-- Elixir (.ex and .exs). Optional: ./scripts/setup-elixir.sh
local elixir_home = vim.env.JETVIM_HOME or vim.env.JETVIM_ROOT .. '/.jetvim'
local elixir_local = elixir_home .. '/tools/elixir-ls/language_server.sh'
local elixir_command = vim.fn.executable(elixir_local) == 1 and elixir_local or 'elixir-ls'
vim.lsp.config('elixirls', {
  cmd = { elixir_command }, filetypes = { 'elixir' },
  root_markers = { 'mix.exs', '.git' },
  settings = { elixirLS = {
    dialyzerEnabled = false, fetchDeps = false, mcpEnabled = false,
  } },
})
if vim.fn.executable(elixir_command) == 1 then vim.lsp.enable('elixirls') end
