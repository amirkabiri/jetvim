#!/usr/bin/env python3
"""Native Elixir syntax and block indentation through an actual editor TUI."""
import json
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='elixir-edit-', dir=STATE) as directory:
    project = Path(directory); (project/'home').mkdir()
    (project/'main.lua').write_text('-- fixture\n')
    code = ['defmodule Example do', '  @answer 42', '  def greet(name) do',
            '    message = "hello # not comment do"', '    atom = :done', '    opts = [key: true]',
            '    value = ~r/do|end/', '    @doc """', '    case fn end', '    """',
            '    # comment do fn end', '    name', '  end', 'end']
    target = project/'example.ex'; target.write_text('\n'.join(code)+'\n')
    script = project/'example.exs'; script.write_text('IO.puts("hello")\n')
    editor = Editor(project, project/'home/settings.lua', disabled=True, disable_lsp=True)
    lua = editor.lua
    def open_file(path):
        editor.raw(b'\x1b[27u')
        lua('require("jetvim.project").open('+json.dumps(str(path))+');return true')
        editor.wait('return vim.api.nvim_buf_get_name(0)=='+json.dumps(str(path)))
    def group(row, text, expected):
        column = len(code[row-1].split(text,1)[0].encode())+1
        equal(lua(f'return vim.fn.synIDattr(vim.fn.synID({row},{column},1),"name")'),expected,text+' has Elixir syntax group')
    def reindent(lines, expected, label):
        editor.raw(b'\x1b[27u')
        lua('vim.api.nvim_buf_set_lines(0,0,-1,false,'+'vim.json.decode('+json.dumps(json.dumps(lines))+')'+');vim.cmd.redraw();vim.cmd.normal({args={"gg=G"},bang=true});return true')
        equal(lua('return vim.api.nvim_buf_get_lines(0,0,-1,false)'),expected,label)
    try:
        open_file(target)
        equal(lua('return {vim.bo.filetype,vim.bo.syntax,vim.bo.shiftwidth,vim.bo.expandtab}'),['elixir','elixir',2,True],'.ex gets Elixir editing options')
        equal(lua('return vim.bo.indentexpr'),'GetJetvimElixirIndent()','Elixir uses native block indentation')
        for row,text,expected in [(1,'defmodule','elixirKeyword'),(1,'Example','elixirModule'),(2,'@answer','elixirAttribute'),
                                  (2,'42','elixirNumber'),(3,'greet','elixirFunction'),(4,'hello','elixirString'),
                                  (4,'#','elixirString'),(5,':done','elixirAtom'),(6,'key','elixirKey'),(6,'true','elixirBoolean'),
                                  (7,'do','elixirSigil'),(9,'case','elixirString'),(11,'#','elixirComment')]:
            group(row,text,expected)
        lua('vim.cmd.redraw();return true')
        equal(lua('local p=vim.fn.screenpos(0,1,1);local cell=vim.api.nvim__inspect_cell(1,p.row-1,p.col-1);'
                  'local c=vim.api.nvim_get_hl(0,{name="Keyword",link=false});return cell[2].foreground==c.fg'),True,'actual TUI keyword cell uses themed syntax color')
        open_file(script)
        equal(lua('return {vim.bo.filetype,vim.bo.syntax}'),['elixir','elixir'],'.exs gets the same Elixir syntax')
        open_file(target)
        reindent(['defmodule Demo do','def pick(value) do','case value do',':ok ->','"do end"','_ ->','nil','end','end','end'],
                 ['defmodule Demo do','  def pick(value) do','    case value do','      :ok ->','        "do end"','      _ ->','        nil','    end','  end','end'],
                 'nested blocks and case clauses indent without counting string keywords')
        reindent(['def run do','Enum.map(values, fn value ->','value + 1','end)','end'],
                 ['def run do','  Enum.map(values, fn value ->','    value + 1','  end)','end'],
                 'anonymous fn arrow opens one indentation level')
        reindent(['if ready do','# do fn end','"end"','else','nil','end','if ready, do: :ok','next()'],
                 ['if ready do','  # do fn end','  "end"','else','  nil','end','if ready, do: :ok','next()'],
                 'comments/strings and inline do colon do not become blocks')
        reindent(['values = [','1,','2',']','result = %{','key: true','}'],
                 ['values = [','  1,','  2',']','result = %{','  key: true','}'],
                 'collection delimiters indent and dedent')
        reindent(['receive do',':ok ->',':done','after','1000 ->',':timeout','end'],
                 ['receive do','  :ok ->','    :done','after','  1000 ->','    :timeout','end'],
                 'receive after and multiple clauses align to their block')
        reindent(['try do','run()','rescue','Error ->','recover()','Other ->','retry()','end'],
                 ['try do','  run()','rescue','  Error ->','    recover()','  Other ->','    retry()','end'],
                 'rescue clause arrows align with their siblings')
        reindent(['def run do','opts = [do: :fn, end: :end]','matcher = ~r/do fn end/','value = "do fn end"','value','end','next()'],
                 ['def run do','  opts = [do: :fn, end: :end]','  matcher = ~r/do fn end/','  value = "do fn end"','  value','end','next()'],
                 'keyword keys, atoms and sigils do not become structural tokens')
        editor.raw(b'\x1b[27u')
        lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{""});vim.api.nvim_win_set_cursor(0,{1,0});vim.cmd.startinsert();return true')
        editor.raw(b'defmodule Typed do\rdef run do\rcase value do\r:ok ->\rwork()\rend\rend\rend')
        equal(lua('return vim.api.nvim_buf_get_lines(0,0,-1,false)'),
              ['defmodule Typed do','  def run do','    case value do','      :ok ->','        work()','    end','  end','end'],
              'actual typed Enter/end/arrow keys maintain nested block indentation')
        editor.raw(b'\x1b[27u')
        lua('local lines={};for i=1,2000 do lines[i]="value = "..string.rep("x",200) end;'
            'vim.api.nvim_buf_set_lines(0,0,-1,false,lines);vim.api.nvim_win_set_cursor(0,{2000,#lines[2000]});vim.cmd.startinsert({bang=true});return true')
        started=time.monotonic();editor.raw(b'\rend')
        elapsed=time.monotonic()-started
        scanned=lua('return vim.b.jetvim_elixir_indent_scanned')
        equal(0 < scanned <= 16384,True,'malformed long context respects shared 16KiB scan budget')
        equal(elapsed < 2,True,'typed unmatched end returns promptly in a 2000-line context')
        equal(lua('return vim.api.nvim_get_current_line()'),'end','bounded fallback preserves typed closing keyword')
        equal(target.read_text(),'\n'.join(code)+'\n','editing fixture does not autosave source')
        equal(lua('return vim.v.errmsg'),'','native Elixir editing leaves no errors')
        print(f'PASS: {support["checks"]} Elixir syntax and indentation TUI checks')
    finally:
        editor.close()
