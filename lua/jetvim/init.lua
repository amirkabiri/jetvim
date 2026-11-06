local M = {}
function M.setup(root)
  require('jetvim.project').setup(vim.env.JETVIM_PROJECT or root)
  local options = {
    number = true, relativenumber = false, mouse = 'a', termguicolors = true,
    expandtab = true, shiftwidth = 2, tabstop = 2, smartindent = true,
    ignorecase = true, smartcase = true, incsearch = true, hlsearch = true,
    splitright = true, splitbelow = true, hidden = true, wrap = false,
    cursorline = true, scrolloff = 5, sidescrolloff = 5, signcolumn = 'yes:3',
    updatetime = 250, timeoutlen = 450, ttimeoutlen = 100,
    laststatus = 3, showtabline = 2, showmode = false,
    selection = 'exclusive', selectmode = 'key', keymodel = 'startsel,stopsel',
    virtualedit = 'onemore', backspace = 'indent,eol,start',
    undofile = true, swapfile = false, backup = false, writebackup = false,
    foldmethod = 'indent', foldlevel = 99, confirm = true,
    exrc = false, modeline = false,
  }
  for key, value in pairs(options) do vim.opt[key] = value end
  if vim.env.JETVIM_SESSION_TITLE then
    vim.o.title = true
    vim.o.titlestring = vim.env.JETVIM_SESSION_TITLE
  end
  local runtime_home = vim.env.JETVIM_HOME or root .. '/.jetvim'
  vim.opt.undodir = runtime_home .. '/undo//'
  vim.fn.mkdir(runtime_home .. '/undo', 'p')
  vim.cmd('filetype plugin indent on')
  vim.cmd('syntax enable')
  vim.cmd.colorscheme('habamax')
  local appearance = dofile(root .. '/config/appearance.lua')
  local theme = require('jetvim.theme')
  theme.setup(appearance)
  vim.opt.fillchars:append({ eob = ' ', vert = '│', horiz = '─', horizup = '┴', horizdown = '┬', vertleft = '┤', vertright = '├', verthoriz = '┼' })
  _G.JetvimStatus = theme.status
  _G.JetvimTabs = theme.tabs
  vim.o.statusline = '%!v:lua.JetvimStatus()'
  vim.o.tabline = '%!v:lua.JetvimTabs()'
  vim.diagnostic.config({ virtual_text = true, signs = true, underline = true, severity_sort = true })
  vim.ui.select = function(items, opts, callback)
    local entries = {}
    for i, item in ipairs(items) do
      entries[#entries + 1] = { label = opts.format_item and opts.format_item(item) or tostring(item), value = item, index = i }
    end
    require('jetvim.ui').pick(opts.prompt or 'Choose', entries, function(item) callback(item.value, item.index) end)
  end
  require('jetvim.keymap').setup(root)
  local group = vim.api.nvim_create_augroup('Jetvim', { clear = true })
  vim.api.nvim_create_autocmd({ 'BufEnter', 'WinEnter' }, { group = group, callback = theme.remember_editor })
  vim.api.nvim_create_autocmd('User', { group = group, pattern = 'JetvimVcsChanged', callback = function()
    vim.cmd.redrawtabline()
  end })
  vim.api.nvim_create_autocmd('BufWritePre', { group = group, callback = function(event)
    local project = require('jetvim.project')
    local settings = package.loaded['jetvim.settings']
    if not project.resolve(event.file) and not project.resolve_tool(event.file)
      and not (settings and settings.allow_path(event.file)) then
      error('Jetvim cannot write outside the selected project or its own configuration directory')
    end
  end })
  vim.api.nvim_create_autocmd('BufWritePost', { group = group, callback = function() require('jetvim.tree').render() end })
  vim.api.nvim_create_autocmd('LspAttach', { group = group, callback = function(event)
    vim.bo[event.buf].omnifunc = 'v:lua.vim.lsp.omnifunc'
  end })
  require('jetvim.lsp').setup(root)
  dofile(root .. '/config/lsp.lua')
  vim.api.nvim_create_user_command('Jetvim', require('jetvim.actions').palette, {})
  vim.api.nvim_create_user_command('JetvimFiles', require('jetvim.actions').files, {})
  vim.api.nvim_create_user_command('JetvimHelp', require('jetvim.actions').help, {})
  vim.api.nvim_create_user_command('JetvimKeyCheck', function()
    print('Press a key (Escape to cancel):')
    local key = vim.fn.getcharstr()
    vim.notify('Received: ' .. vim.fn.keytrans(key))
  end, {})
  vim.api.nvim_create_autocmd('VimEnter', { group = group, once = true, callback = function()
    if #vim.api.nvim_list_uis() == 0 then return end
    if vim.fn.argc() == 0 then
      vim.api.nvim_buf_set_lines(0, 0, -1, false, {
        '', '    J E T V I M', '', '    A terminal editor for JetBrains users.', '',
        '    ⌘1      Project tree', '    ⌘⇧O     Go to File', '    ⌘⇧A     Find Action',
        '    ⌘E      Recent Files', '    ⌘S      Save All', '',
        '    Typing works immediately. Escape enters Vim mode.',
        '    Without a terminal profile: Esc, then Space f opens files.',
        '    Esc, then Space ? opens the shortcut guide.', '',
        '    First launch? See README.md for terminal shortcut setup.',
      })
      vim.bo.buftype = 'nofile'
      vim.bo.bufhidden = 'wipe'
      vim.bo.buflisted = false
      vim.bo.modifiable = false
    end
    local editor = vim.api.nvim_get_current_win()
    require('jetvim.tree').focus()
    vim.api.nvim_set_current_win(editor)
    if vim.bo.modifiable then vim.cmd.startinsert() end
  end })
  require('jetvim.vcs').setup()
  require('jetvim.gutter').setup()
  require('jetvim.settings').setup(root)
  require('jetvim.autosave').setup()
  require('jetvim.disk').setup()
  require('jetvim.hooks').setup()
  require('jetvim.blame').setup()
  require('jetvim.overview').setup()
end
return M
