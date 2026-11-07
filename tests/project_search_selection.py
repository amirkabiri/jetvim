#!/usr/bin/env python3
"""Contiguous Find in Files result selection through real terminal input."""
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='project-search-selection-', dir=STATE) as directory:
    project = Path(directory)
    (project / 'home').mkdir()
    (project / 'main.lua').write_text('-- origin unchanged\n')
    matches = ''.join('needle result %02d\n' % number for number in range(1, 41))
    (project / 'matches.txt').write_text(matches)
    editor = Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    lua = editor.lua
    bindings = json.loads((ROOT / 'config/keymap.json').read_text())
    relay = {item['id']: f'\x1b[{0xF0000 + index}u'.encode() for index, item in enumerate(bindings, 1)}
    def state():
        return lua('local s=require("jetvim.project_search").state;return {selected=s.selected,anchor=s.anchor or 0,'
                   'query=s.query,text=vim.api.nvim_buf_get_lines(s.input,0,1,false)[1],'
                   'height=vim.api.nvim_win_get_height(s.listwin),footer=vim.api.nvim_win_get_config(s.listwin).footer,'
                   'lines=vim.api.nvim_buf_get_lines(s.results,0,-1,false),'
                   'marks=vim.api.nvim_buf_get_extmarks(s.results,vim.api.nvim_create_namespace("JetvimProjectSearch"),0,-1,{details=true})}')
    def selected(active, anchor, label):
        snapshot = state()
        footer = snapshot['footer']
        if isinstance(footer, list):
            footer = ''.join(part[0] for part in footer)
        equal([snapshot['selected'], snapshot['anchor']], [active, anchor], label)
        equal(snapshot['query'], snapshot['text'], 'selection does not edit query')
        equal(lua('return vim.fn.mode()'), 'i', 'result selection retains query typing mode')
        equal(any(line.startswith(' › ') for line in snapshot['lines']), True, 'active result stays visible')
        start, end = min(anchor or active, active), max(anchor or active, active)
        first = max(1, active - snapshot['height'] + 1)
        expected_marks = min(end, first + len(snapshot['lines']) - 1) - max(start, first) + 1
        equal(len(snapshot['marks']), expected_marks, 'every visible selected result is highlighted')
        if anchor:
            equal(f'{end-start+1} selected' in footer, True, 'footer counts complete range')
        else:
            equal(' selected' in footer, False, 'collapsed range clears selection count')
    try:
        editor.raw(b'\x1b[27u')
        editor.raw(b'\x1b[102;10u')
        editor.wait('return require("jetvim.project_search").state~=nil and vim.fn.mode()=="i"')
        editor.raw(b'needle')
        editor.wait('local s=require("jetvim.project_search").state;return s and #s.items==40 and not s.busy and not s.timer')
        selected(1, 0, 'initial result')
        editor.raw(b'\x1b[B'); selected(2, 0, 'plain Down moves one result')
        editor.raw(b'\x1b[1;2B'); selected(3, 2, 'ShiftDown anchors initial result')
        editor.raw(b'\x1b[1;2B'); selected(4, 2, 'repeated ShiftDown grows range')
        editor.raw(b'\x1b[1;2A'); selected(3, 2, 'ShiftUp reverses and shrinks range')
        editor.raw(b'\x1b[1;2A'); selected(2, 2, 'range shrinks to anchor')
        editor.raw(b'\x1b[1;2A'); selected(1, 2, 'range crosses anchor')
        editor.raw(b'\x1b[1;2A'); selected(1, 2, 'range clamps at first result')
        editor.raw(b'\x1b[B'); selected(2, 0, 'plain Down collapses to range end')
        editor.raw(b'\x1b[1;2A'); selected(1, 2, 'upward range starts from collapsed result')
        editor.raw(b'\x1b[A'); selected(1, 0, 'plain Up collapses to range start')
        height = state()['height']
        editor.raw(b'\x1b[6;2~'); selected(1 + height, 1, 'ShiftFnDown selects one visible page')
        editor.raw(b'\x1b[6;2~'); selected(1 + 2 * height, 1, 'page selection scrolls active result into view')
        editor.raw(b'\x1b[5;2~'); selected(1 + height, 1, 'ShiftFnUp shrinks by a page')
        editor.raw(b'\x1b[5;2~'); selected(1, 1, 'reversed page reaches original anchor')
        editor.raw(b'\x1b[1;2F'); selected(40, 1, 'ShiftEnd extends to final result')
        editor.raw(b'\x1b[6;2~'); selected(40, 1, 'page down clamps at final result')
        editor.raw(b'\x1b[1;2H'); selected(1, 1, 'ShiftHome reverses to first result')
        editor.raw(relay['select_file_end']); selected(40, 1, 'private bridge boundary key selects to end')
        editor.raw(relay['select_file_start']); selected(1, 1, 'private bridge boundary key selects to start')
        editor.raw(b'\x1b[6~'); selected(1 + height, 0, 'plain PageDown clears range and moves page')
        editor.raw(b'\x1b[5~'); selected(1, 0, 'plain PageUp moves back one page')
        editor.raw(b'\x1b[1;2B'); selected(2, 1, 'range before query edit')
        editor.raw(b'\x7f')
        editor.wait('local s=require("jetvim.project_search").state;return s.query=="needl" and #s.items==40 and not s.busy and not s.timer')
        selected(1, 0, 'query edit resets anchor and active result')
        editor.raw(b'\x1b[6;2~')
        current = state()['selected']
        target = lua('local s=require("jetvim.project_search").state;return s.items[s.selected]')
        editor.raw(b'\r')
        editor.wait('return require("jetvim.project_search").state==nil and vim.api.nvim_buf_get_name(0)=='+json.dumps(target['path']))
        editor.wait('return vim.fn.mode()=="i"')
        equal(lua('return vim.api.nvim_win_get_cursor(0)'), [target['line'], target['col']], 'Enter opens active result from range')
        equal(target['line'], current, 'active result has expected matching line')
        editor.raw(b'\x1b[27u'); editor.raw(relay['find_project'])
        editor.wait('return require("jetvim.project_search").state~=nil and vim.fn.mode()=="i"')
        editor.raw(b'\x1b[1;2A\x1b[6;2~\x1b[1;2F')
        equal(lua('local s=require("jetvim.project_search").state;return {#s.items,s.anchor or 0,s.selected}'), [0, 0, 1], 'selection keys safely ignore empty result list')
        editor.raw(b'\x1b[27u'); editor.wait('return require("jetvim.project_search").state==nil')
        # Streamed results may arrive while a range is already selected. Their
        # generation must not reset its anchor or revive a prior query's range.
        lua('_G.RangeJobs={};_G.RangeOriginalSystem=vim.system;vim.system=function(argv,opts,done) '
            'if argv[1]~="rg" then return _G.RangeOriginalSystem(argv,opts,done) end;'
            'local job={opts=opts,done=done,killed=false};job.kill=function(self)self.killed=true end;'
            'table.insert(_G.RangeJobs,job);return job end;return true')
        editor.raw(relay['find_project']); editor.wait('return require("jetvim.project_search").state~=nil and vim.fn.mode()=="i"')
        editor.raw(b'needle'); editor.wait('return #_G.RangeJobs==1')
        def stream(job, first, last):
            entries = ''.join(json.dumps({'type': 'match', 'data': {
                'path': {'text': 'matches.txt'}, 'lines': {'text': f'needle result {row}\n'},
                'line_number': row, 'submatches': [{'start': 0}]}})+'\n' for row in range(first, last+1))
            lua(f'_G.RangeJobs[{job}].opts.stdout(nil,'+json.dumps(entries)+');return true')
        stream(1, 1, 8)
        editor.wait('return #require("jetvim.project_search").state.items==8')
        editor.raw(b'\x1b[1;2B' * 3); selected(4, 1, 'held ShiftDown chords in one packet extend range')
        stream(1, 9, 30)
        editor.wait('return #require("jetvim.project_search").state.items==30')
        selected(4, 1, 'appended asynchronous results preserve active row and anchor')
        editor.raw(b'x'); editor.wait('return #_G.RangeJobs==2')
        equal(lua('return _G.RangeJobs[1].killed'), True, 'query edit cancels streaming search with selected range')
        stream(1, 31, 35)
        lua('_G.RangeJobs[1].done({code=0});return true')
        equal(lua('local s=require("jetvim.project_search").state;return {#s.items,s.anchor or 0,s.selected,s.query}'),
              [0, 0, 1, 'needlex'], 'stale query callbacks cannot revive selection or results')
        stream(2, 1, 2); lua('_G.RangeJobs[2].done({code=0});return true')
        editor.wait('local s=require("jetvim.project_search").state;return #s.items==2 and not s.busy')
        selected(1, 0, 'new query results retain cleared range')
        lua('vim.system=_G.RangeOriginalSystem;return true')
        editor.raw(b'\x1b[27u'); editor.wait('return require("jetvim.project_search").state==nil')
        equal((project / 'matches.txt').read_text(), matches, 'selection never changes matching file')
        equal((project / 'main.lua').read_text(), '-- origin unchanged\n', 'selection never changes origin file')
        equal(lua('return vim.v.errmsg'), '', 'selection leaves no editor error')
        print(f'PASS: {support["checks"]} project search range selection terminal checks')
    finally:
        editor.close()
