#!/usr/bin/env python3
"""Held tree arrows use cached row order, preserving every PTY repeat."""
import json
import os
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='tree-navigation-', dir=STATE) as directory:
    project = Path(directory)
    (project / 'home').mkdir()
    (project / 'main.lua').write_text('-- unchanged\n')
    for group in range(4):
        folder = project / f'group{group:02d}'; folder.mkdir()
        for item in range(320):
            (folder / f'file{item:04d}.txt').write_text('fixture\n')
    editor = Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    lua = editor.lua
    try:
        lua('''
          local t=require('jetvim.tree');t.focus()
          for i=0,3 do t.expanded[require('jetvim.project').root..'/group'..string.format('%02d',i)]=true end
          t.render();vim.api.nvim_win_set_cursor(t.win,{2,0})
          _G.nav_original={system=vim.system,sort=table.sort,pairs=pairs,ipairs=ipairs,
            scan=vim.uv.fs_scandir,lines=vim.api.nvim_buf_set_lines,clear=vim.api.nvim_buf_clear_namespace,
            fuzzy=vim.fn.matchfuzzypos,move=t.move,render=t.render,search=t.update_search}
          _G.nav_counts={};_G.nav_trace={};_G.nav_observing=false
          local function count(key)if nav_observing then nav_counts[key]=(nav_counts[key]or 0)+1 end end
          vim.system=function(argv,opts,callback)
            count('jobs')
            local result={code=0,signal=0,stderr='',stdout=''}
            if vim.tbl_contains(argv,'--show-toplevel')then result.stdout=require('jetvim.project').root..'\\n'end
            if callback then vim.schedule(function()callback(result)end)end
            return {kill=function()end,wait=function()return result end}
          end
          table.sort=function(values,comparison)if #values>1000 then count('large_sorts')end;return nav_original.sort(values,comparison)end
          pairs=function(values)if values==t.rows then count('row_scans')end;return nav_original.pairs(values)end
          ipairs=function(values)if values==t.matches then count('match_scans')end;return nav_original.ipairs(values)end
          vim.uv.fs_scandir=function(...)count('scans');return nav_original.scan(...)end
          vim.api.nvim_buf_set_lines=function(buf,...)if buf==t.buf then count('writes')end;return nav_original.lines(buf,...)end
          vim.api.nvim_buf_clear_namespace=function(buf,...)if buf==t.buf then count('namespace_clears')end;return nav_original.clear(buf,...)end
          vim.fn.matchfuzzypos=function(...)count('fuzzy');return nav_original.fuzzy(...)end
          t.move=function(direction)
            count('moves');nav_original.move(direction)
            if nav_observing then nav_trace[#nav_trace+1]=vim.api.nvim_win_get_cursor(t.win)[1]end
          end
          t.render=function(...)count('renders');return nav_original.render(...)end
          t.update_search=function(...)count('search_updates');return nav_original.search(...)end
          vim.env.JETVIM_DISABLE_VCS=nil;require('jetvim.vcs').refresh()
          return true
        ''')
        editor.wait('local v=require("jetvim.vcs");return v._project==require("jetvim.project").root and v._job==nil')
        time.sleep(.6)
        equal(lua('local n=0;for _ in pairs(require("jetvim.tree").rows)do n=n+1 end;return n>1280'), True, 'fixture expands over 1280 entries')

        def repeat(chord, count, paced=False):
            lua('_G.nav_counts={};_G.nav_trace={};_G.nav_observing=true;return true')
            started = time.monotonic()
            if paced:
                for _ in range(count):
                    os.write(editor.master, chord)
                    time.sleep(.004)
            else:
                os.write(editor.master, chord * count)
            editor.wait('return (nav_counts.moves or 0)>=' + str(count), seconds=10)
            lua('_G.nav_observing=false;return true')
            result = lua('return {counts=nav_counts,trace=nav_trace}')
            print('tree navigation observation:', json.dumps({'elapsed_seconds': round(time.monotonic()-started,4), **result['counts']}, sort_keys=True), flush=True)
            equal(result['counts']['moves'], count, 'every held repeat dispatches exactly once')
            for key in ('large_sorts','row_scans','match_scans','scans','writes','fuzzy','jobs','renders','search_updates','namespace_clears'):
                equal(result['counts'].get(key,0), 0, 'held navigation has no '+key)
            return result['trace']

        down, up = b'\x1b[B', b'\x1b[A'
        rows = lua('local t=require("jetvim.tree");local r={};for row in pairs(t.rows)do r[#r+1]=row end;table.sort(r);return r')
        trace = repeat(down, 180)
        equal(trace, rows[1:181], 'burst Down visits every row in order and skips header gap')
        trace = repeat(up, 180, paced=True)
        equal(trace, list(reversed(rows[:180])), 'paced Up preserves key order back to root')
        equal(repeat(up, 12), [2]*12, 'Up clamps at project root')
        lua('local t=require("jetvim.tree");vim.api.nvim_win_set_cursor(t.win,{' + str(rows[-1]) + ',0});return true')
        equal(repeat(down, 12), [rows[-1]]*12, 'Down clamps at final entry')
        editor.raw('file')
        editor.wait('return require("jetvim.tree").query=="file"')
        matches = lua('return require("jetvim.tree").matches')
        equal(len(matches), 1280, 'Speed Search matches expanded files')
        lua('local t=require("jetvim.tree");vim.api.nvim_win_set_cursor(t.win,{t.matches[1],0});return true')
        equal(repeat(down, 180), matches[1:181], 'search repeats follow cached match order')
        lua('local t=require("jetvim.tree");vim.api.nvim_win_set_cursor(t.win,{t.matches[1],0});return true')
        equal(repeat(up, 12), list(reversed(matches[-12:])), 'search Up wraps through cached matches')
        editor.raw(b'\x1b[27u')
        editor.wait('return require("jetvim.tree").query==""')
        # Rebuild after a structural change, then verify cached parent/child rows.
        lua('local t=require("jetvim.tree");vim.api.nvim_win_set_cursor(t.win,{4,0});t.left();return true')
        equal(lua('return require("jetvim.tree").expanded[require("jetvim.project").root.."/group00"]'), False, 'Left collapses current expanded folder')
        equal(repeat(down,1), [5], 'row cache updates after folder collapse')
        editor.raw(b'\x1b[D\x1b[D')
        equal(lua('return vim.api.nvim_win_get_cursor(require("jetvim.tree").win)[1]'), 2, 'Left on closed sibling selects its parent')
        # Skipping fresh-tool annotation cleanup must not retain old editor marks.
        equal(lua('''
          local b=vim.api.nvim_create_buf(false,true);vim.bo[b].buftype=''
          vim.api.nvim_buf_set_name(b,require('jetvim.project').root..'/annotation-fixture.lua')
          vim.api.nvim_buf_set_lines(b,0,-1,false,{'one','two'})
          local blame=require('jetvim.blame');local api=require('jetvim.api')
          blame.states[b]={tick=vim.api.nvim_buf_get_changedtick(b),lines={'Example · Change','Example · Change'}}
          local getter=require('jetvim.settings').get;local settings=getter()
          settings.git.blame={enabled=true,mode='all'};require('jetvim.settings').get=function()return settings end
          blame.render(b)
          local ns=api.namespaces['annotations:git-blame'];local initial=#vim.api.nvim_buf_get_extmarks(b,ns,0,-1,{})
          settings.git.blame.enabled=false;blame.refresh(b)
          local disabled=#vim.api.nvim_buf_get_extmarks(b,ns,0,-1,{})
          local no_state=blame.states[b]==nil
          settings.git.blame.enabled=true
          blame.states[b]={tick=vim.api.nvim_buf_get_changedtick(b),lines={'Example · Change','Example · Change'}}
          blame.render(b);vim.api.nvim_buf_set_lines(b,0,1,false,{'changed'});blame.render(b)
          local stale=#vim.api.nvim_buf_get_extmarks(b,ns,0,-1,{})
          require('jetvim.settings').get=getter;vim.api.nvim_buf_delete(b,{force=true})
          return {initial,disabled,no_state,stale}
        '''), [2,0,True,0], 'previous blame annotations clear on disabled refresh and invalid cache')
        equal(lua('return vim.v.errmsg'), '', 'held navigation leaves no editor errors')
        print(f'PASS: {support["checks"]} tree navigation/cache checks through actual PTY repeat')
    finally:
        try:
            lua('''
              nav_observing=false
              if nav_original then
                local o=nav_original;local t=require('jetvim.tree')
                vim.system=o.system;table.sort=o.sort;pairs=o.pairs;ipairs=o.ipairs;vim.uv.fs_scandir=o.scan
                vim.api.nvim_buf_set_lines=o.lines;vim.api.nvim_buf_clear_namespace=o.clear;vim.fn.matchfuzzypos=o.fuzzy
                t.move=o.move;t.render=o.render;t.update_search=o.search
              end
              vim.env.JETVIM_DISABLE_VCS='1';return true
            ''')
        except Exception:
            pass
        editor.close()
