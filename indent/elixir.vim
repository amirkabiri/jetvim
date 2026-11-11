" Lightweight, syntax-aware block indentation. Mix format remains authoritative.
if exists('b:did_indent')
  finish
endif
let b:did_indent = 1
setlocal indentexpr=GetJetvimElixirIndent()
setlocal indentkeys=o,O,!^F,0=end,0=else,0=rescue,0=catch,0=after,0->,0],0},0)
let b:undo_indent = 'setlocal indentexpr< indentkeys<'

if exists('*GetJetvimElixirIndent')
  finish
endif

function! s:Code(lnum) abort
  let text = getline(a:lnum)
  " Examine syntax only at structural tokens, never at every character.
  if strlen(text) > 4096 | return '' | endif
  if strlen(text) > s:budget
    let s:exhausted = 1
    return ''
  endif
  let s:budget -= strlen(text)
  let result = []
  let position = 0
  while position < strlen(text)
    if reltimefloat(reltime(s:started)) > 0.020
      let s:exhausted = 1
      return ''
    endif
    let found = matchstrpos(text, '\<\h[[:alnum:]_!?]*\>\|->\|[][{}().:]', position)
    if found[1] < 0 | break | endif
    call add(result, repeat(' ', found[1] - position))
    let group = synIDattr(synID(a:lnum, found[1] + 1, 1), 'name')
    let ignored = group =~# '^elixir\%(String\|Sigil\|Comment\|Todo\|Atom\|Key\|Attribute\|Module\|Function\)$'
    call add(result, ignored ? repeat(' ', strlen(found[0])) : found[0])
    let position = found[2]
  endwhile
  return join(result, '')
endfunction

function! s:Tokens(text) abort
  let result = []
  let position = 0
  while position < strlen(a:text)
    let found = matchstrpos(a:text, '\%([.:]\)\@<!\<\%(do\|fn\|end\)\>\%(:\)\@!\|[\[\]{}()]', position)
    if found[1] < 0 | break | endif
    call add(result, found[0])
    let position = found[2]
  endwhile
  return result
endfunction

function! s:Opener(lnum, wanted) abort
  let depth = 0
  " Bounded work for malformed buffers; ordinary continuation uses only one line.
  for row in range(a:lnum - 1, max([1, a:lnum - 2000]), -1)
    let tokens = reverse(s:Tokens(s:Code(row)))
    if s:exhausted | return 0 | endif
    for token in tokens
      if a:wanted ==# 'block'
        if token ==# 'end'
          let depth += 1
        elseif token ==# 'do' || token ==# 'fn'
          if depth == 0 | return row | endif
          let depth -= 1
        endif
      elseif token ==# a:wanted
        if depth == 0 | return row | endif
        let depth -= 1
      elseif token ==# get({'[': ']', '{': '}', '(': ')'}, a:wanted, '')
        let depth += 1
      endif
    endfor
  endfor
  return 0
endfunction

function! GetJetvimElixirIndent() abort
  let s:budget = 16384
  let s:started = reltime()
  let s:exhausted = 0
  let b:jetvim_elixir_indent_scanned = 0
  try
  let previous = prevnonblank(v:lnum - 1)
  if previous == 0 | return 0 | endif
  let current = s:Code(v:lnum)
  let before = s:Code(previous)
  if s:exhausted | return indent(previous) | endif
  let width = shiftwidth()
  if current =~# '^\s*\%(end\|else\|rescue\|catch\|after\)\>\%(:\)\@!'
    let opener = s:Opener(v:lnum, 'block')
    return s:exhausted ? indent(previous) : (opener ? indent(opener) : max([0, indent(previous) - width]))
  endif
  if current =~# '^\s*[]})]'
    let opening = get({']': '[', '}': '{', ')': '('}, matchstr(current, '[]})]'), '')
    let opener = s:Opener(v:lnum, opening)
    return s:exhausted ? indent(previous) : (opener ? indent(opener) : max([0, indent(previous) - width]))
  endif
  if current =~# '->' && current !~# '\<fn\>'
    let opener = s:Opener(v:lnum, 'block')
    if s:exhausted | return indent(previous) | endif
    if opener && s:Code(opener) =~# '\<\%(case\|cond\|receive\|fn\|try\|with\)\>'
      return indent(opener) + width
    endif
  endif
  let balance = 0
  for token in s:Tokens(before)
    let balance += token ==# 'end' || token =~# '^[]})]$' ? -1 : 1
  endfor
  if balance > 0 || before =~# '->\s*$' || before =~# '^\s*\%(else\|rescue\|catch\|after\)\>\%(:\)\@!'
    return indent(previous) + width
  endif
  return indent(previous)
  finally
    let b:jetvim_elixir_indent_scanned = 16384 - s:budget
  endtry
endfunction
