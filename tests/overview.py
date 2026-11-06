#!/usr/bin/env python3
"""Right-edge whole-file diagnostics through actual TUI cells and mouse input."""
import json
import os
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/layout.py')}
exec((ROOT / 'tests/layout.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
lua, wait, raw, equal = (support[key] for key in ('lua', 'wait', 'raw', 'equal'))
STATE, ENV = support['STATE'], support['ENV']
SOCKET = STATE / f'overview-{os.getpid()}.sock'
support['SOCKET'] = SOCKET


def geometry():
    return lua('local list={}; for _,w in ipairs(vim.api.nvim_tabpage_list_wins(0)) do '
               'if vim.api.nvim_win_get_config(w).relative=="" then list[#list+1]={w,vim.api.nvim_win_get_width(w),vim.api.nvim_win_get_height(w),vim.api.nvim_win_get_position(w)} end end; return list')


def set_diagnostics(buf, diagnostics):
    lua('vim.diagnostic.set(vim.api.nvim_create_namespace("OverviewTest"),' + str(buf) + ',vim.json.decode(' + json.dumps(json.dumps(diagnostics)) + ')); return true')


with tempfile.TemporaryDirectory(prefix='overview-', dir=STATE) as directory:
    project = Path(directory)
    (project / 'sample.lua').write_text('\n'.join('local value_' + str(i) + ' = ' + str(i) for i in range(1, 1001)) + '\n')
    fcntl, pty, select = (support[key] for key in ('fcntl', 'pty', 'select'))
    struct, subprocess, termios, threading = (support[key] for key in ('struct', 'subprocess', 'termios', 'threading'))
    master, slave = pty.openpty()
    support['master'] = master
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 35, 140, 0, 0))
    process = subprocess.Popen([str(ROOT / 'jetvim'), directory, 'sample.lua', '--listen', str(SOCKET)],
                               cwd=ROOT, env=ENV, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    stop, output = threading.Event(), bytearray()

    def drain():
        while not stop.is_set():
            readable, _, _ = select.select([master], [], [], 0.1)
            if readable:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    return
                if not data:
                    return
                output.extend(data)
                if b'\x1b]11;?' in data:
                    os.write(master, b'\x1b]11;rgb:1e1e/1f1f/2222\x07')
                if b'\x1b[5n' in data:
                    os.write(master, b'\x1b[0n')

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 10
        while not SOCKET.exists():
            assert process.poll() is None and time.monotonic() < deadline, 'startup failed'
            time.sleep(0.03)
        wait('return package.loaded["jetvim.overview"] ~= nil')
        wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0))', 'sample.lua')
        owner = lua('return vim.api.nvim_get_current_win()')
        buf = lua('return vim.api.nvim_get_current_buf()')
        baseline, caret = geometry(), lua('return vim.api.nvim_win_get_cursor(0)')
        equal(lua('return vim.tbl_count(require("jetvim.overview").panes)'), 0, 'no diagnostics means no overview windows')
        diagnostics = [
            dict(lnum=0, col=0, severity=2, message='top warning'),
            dict(lnum=250, col=0, severity=4, message='hint'),
            dict(lnum=500, col=0, severity=2, message='middle warning'),
            dict(lnum=501, col=0, severity=3, message='colliding info'),
            dict(lnum=502, col=0, severity=4, message='colliding hint'),
            dict(lnum=750, col=0, severity=3, message='information'),
            dict(lnum=999, col=0, severity=1, message='offscreen bottom error'),
        ]
        set_diagnostics(buf, diagnostics)
        wait(f'return require("jetvim.overview").panes[{owner}] ~= nil')
        equal(geometry(), baseline, 'overview floats never change split geometry')
        equal(lua('return vim.api.nvim_get_current_win()'), owner, 'render never steals editor focus')
        equal(lua('return vim.api.nvim_win_get_cursor(0)'), caret, 'render never moves caret')
        height = lua('return vim.api.nvim_win_get_height(0)')
        middle = 500 * (height - 1) // 999
        equal(lua(f'return require("jetvim.overview").panes[{owner}].cells[0].severity'), 2, 'first-file warning maps to top edge')
        equal(lua(f'return require("jetvim.overview").panes[{owner}].cells[{height - 1}].line'), 1000, 'offscreen final-file error maps to bottom edge')
        equal(lua(f'return require("jetvim.overview").panes[{owner}].cells[{middle}].severity'), 2, 'collision keeps strongest severity')
        for group, color in [('Error', 0xE06C75), ('Warning', 0xD9BB76), ('Info', 0x6C95EB), ('Hint', 0x868A91)]:
            equal(lua('return vim.api.nvim_get_hl(0,{name="JetvimOverview' + group + '",link=false}).fg'), color, group + ' marker foreground')
        config = lua(f'return vim.api.nvim_win_get_config(require("jetvim.overview").panes[{owner}].win)')
        equal(config['width'], 1, 'overview is exactly one column')
        equal(config['height'], height, 'overview spans editor text height')
        equal(config['col'], lua('return vim.api.nvim_win_get_width(0)-1'), 'overview anchors inside right edge')
        equal(lua(f'return require("jetvim.tree").is_editor_window(require("jetvim.overview").panes[{owner}].win)'), False, 'overview cannot be selected as editor slot')
        lua('pcall(vim.api.nvim__inspect_cell,1,0,0); vim.cmd("redraw!"); return true')
        time.sleep(0.05)
        grid = lua('local rows={}; for r=0,vim.o.lines-1 do local cells={}; for c=0,vim.o.columns-1 do cells[#cells+1]=vim.api.nvim__inspect_cell(1,r,c) end; rows[#rows+1]=cells end; return rows')
        stripe_position = lua(f'return vim.api.nvim_win_get_position(require("jetvim.overview").panes[{owner}].win)')
        # Native floats have their own grid: inspect that real grid rather than
        # mistaking the underlying editor grid for the composed screen.
        stripe_grid = lua('for id=2,128 do local ok,cell=pcall(vim.api.nvim__inspect_cell,id,0,0); '
                          'if ok and cell and cell[1]=="█" and cell[2].foreground==0xD9BB76 then return id end end; return nil')
        equal(isinstance(stripe_grid, int), True, 'actual floating TUI grid is present')
        stripe_cells = lua(f'local cells={{}}; for r=0,{height-1} do cells[#cells+1]=vim.api.nvim__inspect_cell({stripe_grid},r,0) end; return cells')
        for row, cell in enumerate(stripe_cells):
            grid[stripe_position[0] + row][stripe_position[1]] = cell
        (STATE / 'overview-grid.json').write_text(json.dumps(grid, ensure_ascii=False))
        (STATE / 'overview-screen.txt').write_text('\n'.join(''.join(cell[0] for cell in row) for row in grid) + '\n')
        for line, color in [(0, 0xD9BB76), (250, 0x868A91), (750, 0x6C95EB), (999, 0xE06C75)]:
            index = line * (height - 1) // 999
            cell = grid[stripe_position[0] + index][stripe_position[1]]
            equal(cell[0], '█', 'actual TUI contains whole-file diagnostic marker')
            equal(cell[1]['foreground'], color, 'actual TUI marker has severity RGB')
        set_diagnostics(buf, diagnostics + [dict(lnum=503, col=0, severity=1, message='strongest middle collision')])
        wait(f'return require("jetvim.overview").panes[{owner}].cells[{middle}].severity', 1)
        equal(geometry(), baseline, 'error collision updates marker without changing panes')
        set_diagnostics(buf, diagnostics)
        wait(f'return require("jetvim.overview").panes[{owner}].cells[{middle}].severity', 2)
        # A real SGR click on a whole-file marker jumps to its offscreen diagnostic.
        position = lua(f'return vim.api.nvim_win_get_position(require("jetvim.overview").panes[{owner}].win)')
        raw(f'\x1b[<0;{position[1] + 1};{position[0] + height}M')
        raw(f'\x1b[<0;{position[1] + 1};{position[0] + height}m')
        wait('return vim.api.nvim_win_get_cursor(0)[1]', 1000)
        equal(lua('return vim.api.nvim_get_current_win()'), owner, 'marker click returns focus to owning editor')
        equal(geometry(), baseline, 'marker click preserves real panes')
        # Reflow responds to both file length and editor geometry.
        lua('vim.api.nvim_buf_set_lines(0,1000,1000,false,{"tail"}); return true')
        wait(f'return require("jetvim.overview").panes[{owner}].cells[{height - 2}] ~= nil')
        lua('vim.api.nvim_win_set_width(require("jetvim.tree").win,42); return true')
        wait(f'return vim.api.nvim_win_get_config(require("jetvim.overview").panes[{owner}].win).col == vim.api.nvim_win_get_width({owner})-1')
        equal(lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)'), 42, 'overview resize does not fight sidebar width')
        lua('vim.bo.modified=false; vim.cmd("belowright split"); return true')
        second = lua('return vim.api.nvim_get_current_win()')
        wait('return vim.tbl_count(require("jetvim.overview").panes)', 2)
        equal(len(geometry()), 3, 'two editor views plus sidebar remain three real panes')
        for editor in (owner, second):
            equal(lua(f'return vim.api.nvim_win_get_config(require("jetvim.overview").panes[{editor}].win).height'), lua(f'return vim.api.nvim_win_get_height({editor})'), 'each editor has independently sized overview')
        # Tool focus hides all overviews and never puts a stripe in the tree.
        raw(b'\x1b[49;9u')
        wait('return vim.bo.filetype', 'jetvim-tree')
        wait('return vim.tbl_count(require("jetvim.overview").panes)', 0)
        equal(lua('return vim.bo.filetype'), 'jetvim-tree', 'overview cleanup does not steal tool focus')
        raw(b'\x1b')
        time.sleep(0.15)
        wait('return vim.bo.buftype', '')
        wait('return vim.tbl_count(require("jetvim.overview").panes)', 2)
        # Existing keyboard diagnostic navigation is preserved.
        lua('vim.api.nvim_win_set_cursor(0,{1,0}); return true')
        raw(b'\x1bOQ')  # F2
        wait('return vim.api.nvim_win_get_cursor(0)[1] > 1')
        equal(lua('return vim.bo.buftype'), '', 'F2 still navigates diagnostics in editor')
        lua('vim.diagnostic.reset(vim.api.nvim_create_namespace("OverviewTest"),' + str(buf) + '); return true')
        wait('return vim.tbl_count(require("jetvim.overview").panes)', 0)
        equal(len(geometry()), 3, 'clearing diagnostics removes only overlays')
        # Closing the file with live diagnostics must close overlays, not real panes.
        set_diagnostics(buf, diagnostics)
        wait('return vim.tbl_count(require("jetvim.overview").panes)', 2)
        before_close = geometry()
        raw(b'\x1b[119;9u')
        wait('return vim.tbl_count(require("jetvim.overview").panes)', 0)
        equal(geometry(), before_close, 'Command-W keeps layout while cleaning diagnostic overview')
        raw(b'\x1b[49;9u')
        wait('return vim.bo.filetype', 'jetvim-tree')
        raw(b'\x1b[49;9u')
        equal(lua('return vim.tbl_count(require("jetvim.overview").panes)'), 0, 'Command-1 toggle leaves no phantom overview/editor')
        equal(lua('return vim.v.errmsg'), '', 'no overview errors')
        print(f'PASS: {support["checks"]} diagnostic overview checks through real TUI and mouse input')
    finally:
        if process.poll() is None:
            try:
                os.write(master, b'\x1b')
                lua('vim.cmd("qa!"); return true')
            except Exception:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        stop.set()
        reader.join(timeout=2)
        (STATE / 'overview-output.log').write_bytes(output)
        os.close(master)
        SOCKET.unlink(missing_ok=True)
