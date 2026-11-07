#!/usr/bin/env python3
"""Pasted file:line[:column] references in file and Search Everywhere pickers."""
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='file-location-', dir=STATE) as directory:
    project = Path(directory)
    (project / 'home').mkdir()
    (project / 'main.lua').write_text('-- source unchanged\n')
    target = project / 'internal/domain/message/builder.go'
    target.parent.mkdir(parents=True)
    content = ['// row ' + str(number) + ' with text' for number in range(1, 301)]
    target.write_text('\n'.join(content) + '\n')
    spaced = project / 'folder with spaces/quoted file.lua'; spaced.parent.mkdir()
    spaced.write_text('first\nsecond location\nthird\n')
    colon = project / 'report:12'; colon.write_text('one\ntwo\nthree\nfour\n')
    (project / 'report').write_text('base one\nbase two\nbase three\n')
    other_colon = project / 'note:part.lua'; other_colon.write_text('one\ntwo\nthree\n')
    plain = project / 'plain.lua'; plain.write_text('-- ordinary file\n')
    editor = Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    lua = editor.lua
    bindings = json.loads((ROOT / 'config/keymap.json').read_text())
    relay = {item['id']: f'\x1b[{0xF0000 + index}u'.encode() for index, item in enumerate(bindings, 1)}
    native_everywhere = b'\x1b[112;10u'
    native_files = b'\x1b[111;10u'
    def search(query, path, cursor, chord=native_everywhere, pasted=False):
        editor.raw(b'\x1b[27u')
        lua('require("jetvim.project").open("main.lua");return true')
        editor.raw(chord)
        editor.wait('return vim.bo.buftype=="prompt" and vim.fn.mode()=="i"')
        payload = query.encode()
        if pasted == 'clipboard':
            lua('_G.LocationClipboard={vim.json.decode('+json.dumps(json.dumps([query]))+'),"v"};return true')
            editor.raw(b'\x1b[118;9u\r')
        else:
            editor.raw((b'\x1b[200~' + payload + b'\x1b[201~' if pasted else payload) + b'\r')
        try:
            editor.wait('return vim.api.nvim_buf_get_name(0)=='+json.dumps(str(path)))
        except AssertionError:
            print('Location failure state:', lua('local windows={};for _,w in ipairs(vim.api.nvim_list_wins()) do local b=vim.api.nvim_win_get_buf(w);windows[#windows+1]={type=vim.bo[b].buftype,lines=vim.api.nvim_buf_get_lines(b,0,8,false)} end;return {mode=vim.fn.mode(),file=vim.api.nvim_buf_get_name(0),errmsg=vim.v.errmsg,windows=windows}'))
            raise
        editor.wait('return vim.fn.mode()=="i"')
        equal(lua('return vim.api.nvim_win_get_cursor(0)'), cursor, 'reference opens requested line/column: '+query)
        equal(lua('return vim.api.nvim_get_current_line()'), path.read_text().splitlines()[cursor[0]-1], 'location syntax never edits file contents')
        equal(lua('return vim.api.nvim_buf_get_lines(vim.fn.bufnr("main.lua"),0,-1,false)'), ['-- source unchanged'], 'paste and Enter never edit the origin buffer')
    try:
        lua('vim.g.clipboard={name="File location fixture",copy={["+"]=function()end,["*"]=function()end},'
            'paste={["+"]=function()return _G.LocationClipboard end,["*"]=function()return _G.LocationClipboard end},cache_enabled=0};'
            'vim.g.loaded_clipboard_provider=nil;vim.cmd("runtime autoload/provider/clipboard.vim");return true')
        search('internal/domain/message/builder.go:274', target, [274, 0], pasted=True)
        search('internal/domain/message/builder.go:274', target, [274, 0], pasted='clipboard')
        search("'internal/domain/message/builder.go:274'", target, [274, 0], chord=relay['everywhere'])
        search('"internal/domain/message/builder.go":274:5', target, [274, 4])
        search('builder.go:3:2', target, [3, 1], chord=relay['files'])
        search('./internal/domain/message/builder.go:0:0', target, [1, 0], chord=native_files)
        search(str(target)+':999:999', target, [300, len(content[-1])])
        search('"folder with spaces/quoted file.lua:2:8"', spaced, [2, 7], pasted=True)
        search('note:part.lua:2', other_colon, [2, 0], chord=native_files)
        # Prefer literal indexed filenames before treating final digits as a line.
        search('report:12', colon, [1, 0])
        search('report:12:4', colon, [4, 0])
        search('"report":2:3', project / 'report', [2, 2])
        search('"report:12":3:2', colon, [3, 1])
        # Plain references continue to work without a location suffix.
        search('plain.lua', plain, [1, 0], chord=native_files)
        for query in ('builder.go:-1', 'builder.go:abc', 'builder.go:', 'builder.go:2:-4'):
            editor.raw(b'\x1b[27u')
            lua('require("jetvim.project").open("main.lua");return true')
            editor.raw(native_everywhere);editor.wait('return vim.bo.buftype=="prompt"')
            editor.raw(query.encode()+b'\r')
            editor.wait('return vim.bo.buftype~="prompt"')
            equal(lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'),'main.lua','invalid suffix opens no unrelated location')
        # The file-only transform must not turn action choices into file opens.
        lua('require("jetvim.actions").line=function() _G.location_action=(_G.location_action or 0)+1 end;return true')
        editor.raw(native_everywhere);editor.wait('return vim.bo.buftype=="prompt"')
        editor.raw(b'Go to Line / Column\r')
        editor.wait('return _G.location_action==1')
        equal(lua('return location_action'),1,'ordinary Search Everywhere action remains callable')
        editor.raw(native_everywhere);editor.wait('return vim.bo.buftype=="prompt" and vim.fn.mode()=="i"')
        editor.raw(b'internal/domain/message/builder.go:274\r\x1b[27u')
        editor.wait('return vim.bo.buftype~="prompt"')
        equal(lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'),'main.lua','Escape cancels a queued Enter before file acceptance')
        equal(lua('local p=require("jetvim.project");local root=p.root;p.root="/";local q=require("jetvim.file_location").new({"nested/file.lua"});p.root=root;return q.query("/nested/file.lua:2")'), 'nested/file.lua', 'filesystem-root projects normalize absolute reference paths')
        equal((project / 'main.lua').read_text(),'-- source unchanged\n','search input leaves source file unchanged')
        equal(target.read_text(),'\n'.join(content)+'\n','line jumps never rewrite target file')
        equal(lua('return vim.v.errmsg'),'','file location queries leave no editor errors')
        print(f'PASS: {support["checks"]} file-location terminal checks')
    finally:
        editor.close()
