local M = {}
function M.setup(root)
  local home = vim.env.JETVIM_HOME or root .. '/.jetvim'
  -- Register safe defaults before loading the user's language-server config.
  -- The later ts_ls block merges its cmd/filetypes/root markers with these.
  local log_directory = home .. '/logs/typescript'
  vim.fn.mkdir(log_directory, 'p')
  local tsserver = { logDirectory = log_directory, logVerbosity = 'off', trace = 'off' }
  local fallback = home .. '/tools/typescript/node_modules/typescript/lib/tsserver.js'
  if vim.uv.fs_stat(fallback) then tsserver.fallbackPath = fallback end
  vim.lsp.config('ts_ls', {
    init_options = { disableAutomaticTypingAcquisition = true, tsserver = tsserver },
  })
  -- The launcher supplies local caches for gopls and its Go subprocesses.
  -- Register before the user's config so cmd/root/filetype choices remain theirs.
  vim.lsp.config('gopls', {
    cmd_env = {
      GOPLSCACHE = home .. '/cache/gopls',
      GOCACHE = home .. '/cache/go-build',
      GOMODCACHE = home .. '/cache/go-mod',
      GOPATH = home .. '/tools/go/path',
      GOTMPDIR = home .. '/tmp',
      TMPDIR = home .. '/tmp',
      GOENV = 'off', GOTELEMETRY = 'off', GOTOOLCHAIN = 'local',
      TEST_TELEMETRY_DIR = home .. '/cache/go-telemetry',
    },
  })
  -- Keep ElixirLS package/build caches local; project builds use .elixir_ls.
  vim.lsp.config('elixirls', {
    cmd_env = {
      MIX_HOME = home .. '/tools/elixir/mix', HEX_HOME = home .. '/tools/elixir/hex',
      MIX_INSTALL_DIR = home .. '/tools/elixir/install',
      REBAR_CACHE_DIR = home .. '/cache/rebar3',
      XDG_CONFIG_HOME = home .. '/config', XDG_CACHE_HOME = home .. '/cache',
      XDG_DATA_HOME = home .. '/data', XDG_STATE_HOME = home .. '/state',
      TMPDIR = home .. '/tmp', ERL_CRASH_DUMP = home .. '/elixir-erl-crash.dump',
    },
  })
  vim.api.nvim_create_user_command('JetvimLspInfo', function()
    local lines = { 'File type: ' .. (vim.bo.filetype ~= '' and vim.bo.filetype or '(none)') }
    local clients = vim.lsp.get_clients({ bufnr = 0 })
    if #clients == 0 then lines[#lines + 1] = 'Attached language servers: none'
    else
      local names = {}
      for _, client in ipairs(clients) do names[#names + 1] = client.name end
      lines[#lines + 1] = 'Attached language servers: ' .. table.concat(names, ', ')
    end
    local executable = vim.fn.exepath('typescript-language-server')
    lines[#lines + 1] = 'TypeScript server: ' .. (executable ~= '' and executable or 'not found on PATH')
    if executable == '' then lines[#lines + 1] = 'Install locally: ' .. root .. '/scripts/setup-typescript.sh' end
    local go_executable = vim.fn.exepath('gopls')
    lines[#lines + 1] = 'Go server: ' .. (go_executable ~= '' and go_executable or 'gopls not found on PATH')
    if go_executable == '' then lines[#lines + 1] = 'Install Go support locally: ' .. root .. '/scripts/setup-gopls.sh' end
    local elixir_local = home .. '/tools/elixir-ls/language_server.sh'
    local elixir_executable = vim.fn.executable(elixir_local) == 1 and elixir_local or vim.fn.exepath('elixir-ls')
    lines[#lines + 1] = 'Elixir server: ' .. (elixir_executable ~= '' and elixir_executable or 'elixir-ls not found on PATH')
    if elixir_executable == '' then lines[#lines + 1] = 'Install Elixir support locally: ' .. root .. '/scripts/setup-elixir.sh' end
    local go_file = vim.tbl_contains({ 'go', 'gomod', 'gowork' }, vim.bo.filetype)
    local ts_file = vim.tbl_contains({ 'javascript', 'javascriptreact', 'typescript', 'typescriptreact' }, vim.bo.filetype)
    local elixir_file = vim.bo.filetype == 'elixir'
    if go_file or ts_file or elixir_file then
      local server = go_file and 'gopls' or (elixir_file and 'elixirls' or 'ts_ls')
      local markers = go_file and { 'go.work', 'go.mod', '.git' }
        or (elixir_file and { 'mix.exs', '.git' } or { 'tsconfig.json', 'package.json', '.git' })
      local workspace = vim.fs.root(vim.api.nvim_buf_get_name(0), markers)
      lines[#lines + 1] = server .. ' enabled: ' .. (vim.lsp.is_enabled(server) and 'yes' or 'no')
      lines[#lines + 1] = 'Matching workspace root: ' .. (workspace or 'none; open a project with ' .. table.concat(markers, ', '))
    end
    if vim.bo.filetype == 'json' or vim.bo.filetype == 'jsonc' then
      lines[#lines + 1] = 'ts_ls supports JavaScript/TypeScript; JSON files need a JSON language server.'
    end
    lines[#lines + 1] = 'Config: ' .. root .. '/config/lsp.lua'
    vim.notify(table.concat(lines, '\n'), vim.log.levels.INFO, { title = 'Jetvim language support' })
  end, { desc = 'Show file type, attached servers, workspace and local executables' })
end
return M
