local M = { mode = 'portable' }
local types = {
  folder = { '▱', '', 'Folder' },
  folder_open = { '▱', '', 'Folder' },
  file = { '◇', '󰈔', 'File' },
  json = { '{}', '', 'Json' },
  javascript = { 'JS', '', 'Javascript' },
  typescript = { 'TS', '', 'Typescript' },
  jsx = { 'JS', '', 'Javascript' },
  tsx = { 'TS', '', 'Typescript' },
  yaml = { 'Y', '', 'Yaml' },
  lua = { '◐', '', 'Lua' },
  python = { 'Py', '', 'Python' },
  go = { 'Go', '', 'Go' },
  elixir = { 'Ex', '', 'Elixir' },
  rust = { 'Rs', '', 'Rust' },
  markdown = { 'M↓', '', 'Markdown' },
  html = { '<>', '', 'Html' },
  css = { '#', '', 'Css' },
  shell = { '>_', '', 'Shell' },
  config = { '⚙', '', 'Config' },
  git = { '◆', '', 'Git' },
}
M.colors = {
  Folder = '#a8adb5', File = '#9da0a8', Json = '#c191d6', Javascript = '#d9bb76',
  Typescript = '#6c95eb', Yaml = '#d18a94', Lua = '#6c95eb', Python = '#d9bb76',
  Elixir = '#c191d6', Go = '#68b8c7', Rust = '#cf8e6d', Markdown = '#6c95eb', Html = '#cf8e6d',
  Css = '#c191d6', Shell = '#6aab73', Config = '#a8adb5', Git = '#e38b59',
}
local extensions = {
  json = 'json', jsonc = 'json', jsonl = 'json', js = 'javascript', mjs = 'javascript',
  cjs = 'javascript', jsx = 'jsx', ts = 'typescript', tsx = 'tsx', yml = 'yaml', yaml = 'yaml',
  ex = 'elixir', exs = 'elixir',
  lua = 'lua', py = 'python', pyw = 'python', go = 'go', mod = 'go', rs = 'rust',
  md = 'markdown', markdown = 'markdown', html = 'html', htm = 'html', css = 'css',
  scss = 'css', sh = 'shell', zsh = 'shell', bash = 'shell', fish = 'shell',
  toml = 'config', ini = 'config', conf = 'config', cfg = 'config', xml = 'config',
}
function M.setup(options)
  M.mode = options and options.icons == 'nerd' and 'nerd' or 'portable'
end
function M.for_path(path, directory, expanded)
  local name = vim.fs.basename(path or ''):lower()
  local kind
  if directory then kind = expanded and 'folder_open' or 'folder'
  elseif name:match('^%.git') or name == 'gitignore' then kind = 'git'
  elseif name == 'dockerfile' or name == 'makefile' or name == '.editorconfig' or name:match('^%.env') then kind = 'config'
  else kind = extensions[name:match('%.([^%.]+)$') or ''] or 'file' end
  local spec = types[kind]
  local text = spec[M.mode == 'nerd' and 2 or 1]
  local padding = math.max(0, 2 - vim.fn.strdisplaywidth(text))
  return { text = text .. string.rep(' ', padding), hl = 'JetvimIcon' .. spec[3], kind = kind }
end
return M
