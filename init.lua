if vim.fn.has('nvim-0.11') == 0 then
  error('Jetvim requires Neovim 0.11 or newer')
end
local root = assert(vim.env.JETVIM_ROOT, 'Start Jetvim with ./jetvim')
vim.opt.runtimepath:prepend(root)
vim.opt.packpath = root
vim.g.mapleader = ' '
vim.g.maplocalleader = ' '
require('jetvim').setup(root)
