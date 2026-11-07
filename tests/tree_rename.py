#!/usr/bin/env python3
"""Tree rename through native/relay keys, buffer state and safe filesystem paths."""
import json
import os
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__':str(ROOT/'tests/autosave.py')}
exec((ROOT/'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory',1)[0],support)
Editor,equal,STATE = support['Editor'],support['equal'],support['STATE']
with tempfile.TemporaryDirectory(prefix='rename-',dir=STATE) as folder:
    project=Path(folder);(project/'home').mkdir()
    preferences=project/'home/settings.lua'
    preferences.write_text('return {autosave={enabled=true,debounce=false,on_focus_lost=false}}\n')
    (project/'main.lua').write_text('first\nsecond\n')
    editor=Editor(project,preferences,disable_lsp=True)
    native=b'\x1b[17;2~'
    bindings=json.loads((ROOT/'config/keymap.json').read_text())
    index=next(i for i,item in enumerate(bindings,1) if item['id']=='rename')
    relay=f'\x1b[{0xF0000+index}u'.encode()
    def lua(code):return editor.lua(code)
    def choose(path):
        editor.raw(b'\x1b[27u')
        result=lua('local t=require("jetvim.tree");t.focus();local parent=vim.fs.dirname('+json.dumps(str(path))+');'
                   'while parent and require("jetvim.project").resolve(parent) do t.expanded[parent]=true;'
                   'if parent==require("jetvim.project").root then break end;parent=vim.fs.dirname(parent) end;'
                   't.clear_search();t.render();for row,e in pairs(t.rows) do if e.path=='+json.dumps(str(path))+' then '
                   'vim.api.nvim_win_set_cursor(t.win,{row,0});return true end end;return false')
        equal(result,True,'rename entry visible')
    def open_file(path):
        lua('require("jetvim.project").open('+json.dumps(str(path))+');return true')
        return lua('return vim.api.nvim_get_current_buf()')
    def mock_input(value,body=''):
        lua('vim.ui.input=function(opts,callback) vim.g.rename_default=opts.default;'+body+' callback('
            +('nil' if value is None else 'vim.json.decode('+json.dumps(json.dumps(value))+')')+') end;return true')
    def rename(path,value,chord=relay,body=''):
        choose(path);mock_input(value,body);editor.raw(chord)
    def autosave(enabled):
        preferences.write_text('return {autosave={enabled=true,debounce='+('true' if enabled else 'false')+',delay_ms=100,on_focus_lost=false}}\n')
        lua('vim.cmd("JetvimReloadSettings");return true')
    def assert_selected(path):
        equal(lua('local t=require("jetvim.tree");return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].path'),str(path),'renamed entry selected')
    try:
        lua('_G.rename_ui_input=vim.ui.input;_G.rename_notices={};vim.notify=function(text)vim.g.rename_last_notice=text;table.insert(_G.rename_notices,text) end;return true')
        source=project/'main.lua';buf=lua('return vim.api.nvim_get_current_buf()')
        choose(source);editor.raw(native)
        editor.wait('return vim.fn.mode()=="c"')
        equal(lua('return vim.fn.getcmdline()'),'main.lua','native rename pre-fills current basename')
        editor.raw(b'\x15renamed.lua\r')
        target=project/'renamed.lua'
        equal(target.read_text(),'first\nsecond\n','native rename preserves disk content')
        equal(source.exists(),False,'native rename removes old name')
        equal(lua('return vim.api.nvim_buf_get_name('+str(buf)+')'),str(target),'open buffer retargeted')
        equal(lua('return vim.bo['+str(buf)+'].modified'),False,'clean rename stays clean')
        assert_selected(target)
        choose(target);editor.raw(relay);editor.wait('return vim.fn.mode()=="c"');editor.raw(b'\x1b')
        equal(target.exists(),True,'real relay cancellation keeps source')
        equal(lua('return vim.b['+str(buf)+'].jetvim_closing'),None,'cancel releases autosave hold')
        choose(target);editor.raw(relay);editor.wait('return vim.fn.mode()=="c"');editor.raw(b'\x15relay.lua\r')
        source=project/'relay.lua'
        equal(source.exists(),True,'relay opens genuine rename prompt')
        # Native re-reading clears overwrite protection without saving dirty text.
        lua('vim.ui.input=_G.rename_ui_input;return true')
        dirty=open_file(source)
        lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{"dirty text"});return true')
        before_undo=lua('return vim.fn.undotree().seq_cur')
        rename(source,'dirty.txt')
        target=project/'dirty.txt'
        equal(target.read_text(),'first\nsecond\n','rename does not prematurely write dirty buffer')
        equal(lua('return vim.api.nvim_buf_get_lines('+str(dirty)+',0,-1,false)'),['dirty text'],'dirty buffer text preserved')
        equal(lua('return vim.bo['+str(dirty)+'].modified'),True,'dirty state preserved')
        equal(lua('return vim.bo['+str(dirty)+'].filetype'),'text','extension rename updates syntax filetype')
        equal(lua('return vim.api.nvim_buf_call('+str(dirty)+',function()return vim.fn.undotree().seq_cur end)'),before_undo,'original undo position preserved')
        autosave(True);editor.disk(target,'dirty text\n')
        equal(source.exists(),False,'dirty rename autosaves only new path')
        autosave(False)
        folder=project/'folder';(folder/'nested').mkdir(parents=True)
        child=folder/'nested/child.lua';child.write_text('child disk\n')
        childbuf=open_file(child)
        lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{"child dirty"});vim.cmd.vsplit();return true')
        choose(folder)
        lua('local t=require("jetvim.tree");t.expanded['+json.dumps(str(folder))+']=true;t.expanded['+json.dumps(str(folder/"nested"))+']=true;t.render();return true')
        geometry=lua('local t=require("jetvim.tree");return {#vim.api.nvim_list_wins(),vim.api.nvim_win_get_width(t.win)}')
        mock_input('renamed folder');editor.raw(native)
        newfolder=project/'renamed folder';newchild=newfolder/'nested/child.lua'
        equal(newchild.read_text(),'child disk\n','folder rename preserves child disk bytes')
        equal(lua('return vim.api.nvim_buf_get_name('+str(childbuf)+')'),str(newchild),'folder rename retargets loaded descendants')
        equal(lua('return vim.api.nvim_buf_get_lines('+str(childbuf)+',0,-1,false)'),['child dirty'],'folder rename preserves child edits')
        equal(lua('local t=require("jetvim.tree");return {#vim.api.nvim_list_wins(),vim.api.nvim_win_get_width(t.win)}'),geometry,'folder rename preserves pane geometry')
        equal(lua('return require("jetvim.tree").expanded['+json.dumps(str(newfolder/'nested'))+']'),True,'expanded descendants follow renamed folder')
        assert_selected(newfolder)
        autosave(True);editor.disk(newchild,'child dirty\n');equal(folder.exists(),False,'folder autosave never recreates old directory')
        autosave(False)
        kittyfile=project/'kitty.lua';kittyfile.write_text('kitty\n');rename(kittyfile,'kitty-new.lua',b'\x1b[57369;2u')
        equal((project/'kitty-new.lua').exists(),True,'Kitty ShiftF6 also performs contextual rename')
        # A prior external conflict is still a conflict after renaming.
        conflict=project/'conflict.lua';conflict.write_text('before\n');conflictbuf=open_file(conflict)
        lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{"local change"});return true')
        conflict.write_text('external change\n')
        rename(conflict,'conflict-new.lua')
        conflicted=conflict
        equal((project/'conflict-new.lua').exists(),False,'preexisting disk conflict blocks rename')
        autosave(True);time.sleep(.35)
        equal(conflicted.read_text(),'external change\n','rename does not authorize overwriting external conflict')
        equal(lua('return vim.api.nvim_buf_get_lines('+str(conflictbuf)+',0,-1,false)'),['local change'],'conflicting local edits preserved')
        equal(conflict.exists(),True,'conflicting source keeps its original native disk guard')
        autosave(False)
        # Invalid/colliding names, including dangling links and open buffer names.
        stable=project/'stable.txt';stable.write_text('stable\n')
        for value in ('','.', '..','../escape','child/name','child\\name','bad\nname','bad\x00name'):
            rename(stable,value);equal(stable.read_text(),'stable\n','invalid rename leaves source unchanged')
        for value in ('existing.txt','dangling.txt','buffer-only.txt'):
            destination=project/value
            if value=='existing.txt':destination.write_text('existing\n')
            elif value=='dangling.txt':destination.symlink_to(project/'missing-target')
            else:lua('vim.fn.bufadd('+json.dumps(str(destination))+');return true')
            rename(stable,value)
            equal(stable.exists(),True,'collision does not remove source')
            if value=='existing.txt':equal(destination.read_text(),'existing\n','collision never overwrites target')
        virtual=project/'virtual-source';virtual.mkdir();(virtual/'child.lua').write_text('original child\n')
        lua('vim.fn.bufadd('+json.dumps(str(project/'virtual-destination/child.lua'))+');return true')
        rename(virtual,'virtual-destination');equal(virtual.exists(),True,'folder rename blocks destination descendant buffer collision')
        rename(stable,None);equal(stable.exists(),True,'callback cancellation keeps source')
        choose(project);mock_input('root-renamed');lua('vim.g.rename_default="untouched";return true');editor.raw(native)
        equal(lua('return vim.g.rename_default'),'untouched','project root cannot be renamed')
        outside=project.parent/('rename-outside-'+str(os.getpid()));outside.mkdir()
        try:
            targetfile=outside/'target';targetfile.write_text('external\n')
            link=project/'link';link.symlink_to(outside,target_is_directory=True)
            rename(link,'renamed-link')
            equal((project/'renamed-link').is_symlink(),True,'rename moves symlink itself')
            equal(targetfile.read_text(),'external\n','link target stays unchanged')
            choose(project);lua('local t=require("jetvim.tree");t.rows[2]={path='+json.dumps(str(targetfile))+'};return true');editor.raw(native)
            equal(targetfile.exists(),True,'forged outside entry protected')
            parentlink=project/'parent-link';parentlink.symlink_to(outside,target_is_directory=True)
            choose(project);lua('local t=require("jetvim.tree");t.rows[2]={path='+json.dumps(str(parentlink/'target'))+'};return true');editor.raw(native)
            equal(targetfile.exists(),True,'symlink parent escape protected')
        finally:
            import shutil
            shutil.rmtree(outside)
        failed=project/'failed.lua';failed.write_text('disk\n');failedbuf=open_file(failed)
        lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{"unsaved failure"});return true')
        choose(failed);mock_input('failed-new.lua');lua('_G.rename_fs=vim.uv.fs_rename;vim.uv.fs_rename=function()return nil,"denied"end;return true')
        editor.raw(relay);lua('vim.uv.fs_rename=_G.rename_fs;return true')
        equal(failed.read_text(),'disk\n','filesystem failure leaves original disk data')
        equal(lua('return vim.api.nvim_buf_get_name('+str(failedbuf)+')'),str(failed),'filesystem failure restores original buffer name')
        equal(lua('return vim.api.nvim_buf_get_lines('+str(failedbuf)+',0,-1,false)'),['unsaved failure'],'filesystem failure preserves unsaved data')
        equal(lua('return vim.b['+str(failedbuf)+'].jetvim_closing'),None,'failure releases autosave hold')
        lua('vim.b['+str(failedbuf)+'].jetvim_hook_running=true;return true')
        rename(failed,'busy.lua');equal(failed.exists(),True,'running save hook blocks rename')
        lua('vim.b['+str(failedbuf)+'].jetvim_hook_running=nil;return true')
        # An empty buffer and one real blank line have identical line arrays.
        for label, diskbytes, replacement, expectedbytes in [('empty',b'old\n',[],b''),('blank',b'',[''],b'\n')]:
            item=project/(label+'.txt');item.write_bytes(diskbytes);emptybuf=open_file(item)
            lua('vim.api.nvim_buf_set_lines(0,0,-1,false,vim.json.decode('+json.dumps(json.dumps(replacement))+'));return true')
            before_empty=lua('return vim.fn.wordcount().bytes==0')
            rename(item,label+'-new.txt')
            equal(lua('return vim.api.nvim_buf_call('+str(emptybuf)+',function()return vim.fn.wordcount().bytes==0 end)'),before_empty,'rename preserves actual empty versus blank state')
            autosave(True);editor.wait('return not vim.bo['+str(emptybuf)+'].modified')
            equal((project/(label+'-new.txt')).read_bytes(),expectedbytes,'renamed empty/blank buffer writes exact byte shape')
            autosave(False)
        casefile=project/'CaseName.lua';casefile.write_text('case content\n');casebuf=open_file(casefile)
        rename(casefile,'casename.lua')
        equal('casename.lua' in {p.name for p in project.iterdir()},True,'case-only rename updates actual directory entry')
        equal('CaseName.lua' in {p.name for p in project.iterdir()},False,'case-only rename removes old spelling')
        equal(lua('return vim.api.nvim_buf_get_name('+str(casebuf)+')'),str(project/'casename.lua'),'case-only rename retargets open buffer')
        hard=project/'HardName.lua';hard.write_text('hard content\n');alias=project/'hardname.lua'
        if not alias.exists():
            os.link(hard,alias);rename(hard,'hardname.lua')
            equal(hard.exists(),True,'distinct existing hardlink is not mistaken for case alias')
            equal(alias.read_text(),'hard content\n','hardlink collision is never overwritten')
        # Native reload preserves readonly/CRLF/BOM/no-final-newline settings.
        encoded=project/'encoded.txt';encoded.write_bytes(b'\xef\xbb\xbffirst\r\nlast')
        encodedbuf=open_file(encoded)
        lua('vim.bo.readonly=true;vim.bo.fixendofline=false;vim.api.nvim_buf_set_lines(0,0,1,false,{"café"});return true')
        rename(encoded,'encoded.md')
        encodednew=project/'encoded.md'
        equal(encodednew.read_bytes(),b'\xef\xbb\xbffirst\r\nlast','readonly rename leaves original disk bytes')
        equal(lua('return {vim.bo['+str(encodedbuf)+'].readonly,vim.bo['+str(encodedbuf)+'].bomb,vim.bo['+str(encodedbuf)+'].endofline,vim.bo['+str(encodedbuf)+'].fileformat}'),[True,True,False,'dos'],'rename preserves readonly and file encoding options')
        lua('vim.bo['+str(encodedbuf)+'].readonly=false;return true');autosave(True)
        editor.wait('return not vim.bo['+str(encodedbuf)+'].modified')
        equal(encodednew.read_bytes(),'\ufeffcafé\r\nlast'.encode(),'renamed dirty buffer saves with original encoding and no final newline')
        autosave(False)
        # A buffer-name failure happens before the filesystem move and restores all names.
        namefail=project/'namefail.lua';namefail.write_text('name disk\n');namebuf=open_file(namefail)
        lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{"name dirty"});return true')
        choose(namefail);mock_input('namefail-new.lua')
        lua('_G.rename_setname=vim.api.nvim_buf_set_name;vim.api.nvim_buf_set_name=function(b,name) if name:find("namefail-new",1,true) then error("name fixture denied") end;return _G.rename_setname(b,name) end;return true')
        editor.raw(native);lua('vim.api.nvim_buf_set_name=_G.rename_setname;return true')
        equal(namefail.exists(),True,'buffer naming failure never moves disk file')
        equal(lua('return vim.api.nvim_buf_get_name('+str(namebuf)+')'),str(namefail),'buffer naming failure keeps original name')
        equal(lua('return vim.api.nvim_buf_get_lines('+str(namebuf)+',0,-1,false)'),['name dirty'],'buffer naming failure preserves dirty text')
        # Edits made by a filename-change observer are preserved on rollback.
        late=project/'late.lua';late.write_text('late disk\n');latebuf=open_file(late)
        lua('vim.api.nvim_create_autocmd("BufFilePost",{group=vim.api.nvim_create_augroup("RenameLateEditTest",{clear=true}),buffer='+str(latebuf)+',callback=function() if vim.api.nvim_buf_get_name(0):find("late-new",1,true) then vim.api.nvim_buf_set_lines(0,0,-1,false,{"late observer edit"}) end end});return true')
        rename(late,'late-new.lua')
        equal(late.exists(),True,'observer edit aborts filesystem rename')
        equal(lua('return vim.api.nvim_buf_get_lines('+str(latebuf)+',0,-1,false)'),['late observer edit'],'observer edits made after snapshot are not lost')
        lua('vim.api.nvim_del_augroup_by_name("RenameLateEditTest");return true')
        # Even a reload that destroys buffer text and then throws cannot lose edits.
        reloadfile=project/'Reload.lua';reloadfile.write_text('reload disk\n');reloadbuf=open_file(reloadfile)
        lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{"precious dirty text"});return true')
        choose(reloadfile);mock_input('reload.lua')
        lua('_G.rename_cmd=vim.cmd;vim.cmd=function(cmd) if type(cmd)=="string" and cmd:find("keepalt edit!",1,true) then vim.api.nvim_buf_set_lines(0,0,-1,false,{"destroyed by reload"});error("reload fixture denied") end;return _G.rename_cmd(cmd) end;return true')
        editor.raw(native);lua('vim.cmd=_G.rename_cmd;return true')
        equal(reloadfile.read_text(),'reload disk\n','failed reload rolls disk name back')
        equal('Reload.lua' in {p.name for p in project.iterdir()},True,'case-only failure restores original directory spelling')
        equal('reload.lua' in {p.name for p in project.iterdir()},False,'case-only rollback removes temporary spelling')
        equal(lua('return vim.api.nvim_buf_get_lines('+str(reloadbuf)+',0,-1,false)'),['precious dirty text'],'failed reload and failed rollback reload preserve original dirty text')
        equal(lua('return vim.b['+str(reloadbuf)+'].jetvim_closing'),True,'incomplete native recovery pauses autosave explicitly')
        equal(lua('return not require("jetvim.autosave").writing and not require("jetvim.disk").reloading and not require("jetvim.tree").renaming'),True,'reload failure always releases global guards')
        equal(lua('return table.concat(_G.rename_notices," "):find("Autosave paused",1,true)~=nil'),True,'incomplete recovery tells user how to recover')
        recovery=list((project/'home/tmp').glob('rename-*'))
        equal(bool(recovery),True,'undo recovery evidence is retained when rollback reload fails')
        for evidence in recovery:evidence.unlink()
        lua('vim.bo['+str(reloadbuf)+'].modified=false;vim.b['+str(reloadbuf)+'].jetvim_closing=nil;return true')
        # Optional annotation failures cannot strand global state after success.
        cleanup=project/'cleanup.lua';cleanup.write_text('cleanup\n');cleanupbuf=open_file(cleanup)
        choose(cleanup);mock_input('cleanup-new.lua')
        lua('vim.api.nvim_del_augroup_by_name("JetvimBlame");_G.rename_blame=require("jetvim.blame").refresh;require("jetvim.blame").refresh=function()error("annotation fixture denied")end;return true')
        editor.raw(native);lua('require("jetvim.blame").refresh=_G.rename_blame;return true')
        equal((project/'cleanup-new.lua').exists(),True,'annotation failure does not roll back successful rename')
        equal(lua('return not require("jetvim.autosave").writing and not require("jetvim.disk").reloading and not require("jetvim.tree").renaming and not vim.b['+str(cleanupbuf)+'].jetvim_closing'),True,'optional cleanup errors do not leave global or buffer guards')
        # Editor ShiftF6 still dispatches the LSP symbol rename.
        open_file(target)
        lua('vim.lsp.get_clients=function()return {{}}end;vim.g.symbol_renames=0;vim.lsp.buf.rename=function()vim.g.symbol_renames=vim.g.symbol_renames+1 end;return true')
        editor.raw(native);editor.raw(relay)
        equal(lua('return vim.g.symbol_renames'),2,'editor native and relay ShiftF6 retain symbol rename')
        equal(lua('return vim.v.errmsg'),'','rename leaves no editor error')
        equal(list((project/'home/tmp').glob('rename-*')),[],'temporary undo snapshots are removed')
        print(f'PASS: {support["checks"]} tree rename and buffer safety checks through actual PTY input')
    finally:editor.close()
