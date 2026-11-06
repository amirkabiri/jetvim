local M = {}
function M.setup(root)
  -- Register safe defaults before loading the user's language-server config.
  -- The later ts_ls block merges its cmd/filetypes/root markers with these.
  local log_directory = root .. '/.jetvim/logs/typescript'
  vim.fn.mkdir(log_directory, 'p')
  local tsserver = { logDirectory = log_directory, logVerbosity = 'off', trace = 'off' }
  local fallback = root .. '/.jetvim/tools/typescript/node_modules/typescript/lib/tsserver.js'
  if vim.uv.fs_stat(fallback) then tsserver.fallbackPath = fallback end
  vim.lsp.config('ts_ls', {
    init_options = { disableAutomaticTypingAcquisition = true, tsserver = tsserver },
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
    if vim.bo.filetype == 'json' or vim.bo.filetype == 'jsonc' then
      lines[#lines + 1] = 'ts_ls supports JavaScript/TypeScript; JSON files need a JSON language server.'
    end
    lines[#lines + 1] = 'Config: ' .. root .. '/config/lsp.lua'
    vim.notify(table.concat(lines, '\n'), vim.log.levels.INFO, { title = 'Jetvim language support' })
  end, { desc = 'Show file type, attached servers and TypeScript executable' })
end
return M
