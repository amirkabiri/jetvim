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
    local go_file = vim.tbl_contains({ 'go', 'gomod', 'gowork' }, vim.bo.filetype)
    local ts_file = vim.tbl_contains({ 'javascript', 'javascriptreact', 'typescript', 'typescriptreact' }, vim.bo.filetype)
    if go_file or ts_file then
      local server = go_file and 'gopls' or 'ts_ls'
      local markers = go_file and { 'go.work', 'go.mod', '.git' } or { 'tsconfig.json', 'package.json', '.git' }
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
