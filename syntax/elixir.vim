" Native Elixir highlighting; no parser download is required.
if exists('b:current_syntax')
  finish
endif
syntax case match
syntax keyword elixirKeyword after alias and case catch cond def defdelegate defexception defguard defguardp defimpl defmacro defmacrop defmodule defp defprotocol defstruct do else end fn for if import in not or quote raise receive require rescue super try unless unquote unquote_splicing use when with
syntax keyword elixirBoolean true false nil
syntax match elixirOperator "[-+*/=<>!|&^~:]\+"
syntax match elixirNumber "\<\d[[:alnum:]_]*\%(\.\d[[:digit:]_]*\)\?\%([eE][-+]\?[[:digit:]_]\+\)\?\>"
syntax match elixirModule "\<[A-Z][[:alnum:]_]*\%(\.[A-Z][[:alnum:]_]*\)*\>"
syntax match elixirAttribute "@\h[[:alnum:]_]*"
syntax match elixirAtom "\%(:\)\@<!:\h[[:alnum:]_!?@]*"
syntax match elixirKey "\<\h[[:alnum:]_!?]*\ze:\%(:\)\@!"
syntax keyword elixirDefine def defp defmacro defmacrop defguard defguardp nextgroup=elixirFunction skipwhite
syntax match elixirFunction "\h[[:alnum:]_!?]*" contained
syntax region elixirString start=+"+ skip=+\\.+ end=+"+
syntax region elixirString start=+'+ skip=+\\.+ end=+'+
syntax region elixirString start=+"""+ end=+^\s*"""+ keepend
syntax region elixirString start=+'''+ end=+^\s*'''+ keepend
syntax region elixirSigil start=+\~[a-zA-Z]/+ skip=+\\.+ end=+/[a-zA-Z]*+
syntax region elixirSigil start=+\~[a-zA-Z]|+ skip=+\\.+ end=+|[a-zA-Z]*+
syntax region elixirSigil start=+\~[a-zA-Z]{+ skip=+\\.+ end=+}[a-zA-Z]*+
syntax region elixirSigil start=+\~[a-zA-Z]\[+ skip=+\\.+ end=+\][a-zA-Z]*+
syntax region elixirSigil start=+\~[a-zA-Z](+ skip=+\\.+ end=+)[a-zA-Z]*+
syntax region elixirSigil start=+\~[a-zA-Z]<+ skip=+\\.+ end=+>[a-zA-Z]*+
syntax region elixirSigil start=+\~[a-zA-Z]"+ skip=+\\.+ end=+"[a-zA-Z]*+
syntax region elixirSigil start=+\~[a-zA-Z]'+ skip=+\\.+ end=+'[a-zA-Z]*+
syntax region elixirSigil start=+\~[a-zA-Z]"""+ end=+^\s*"""[a-zA-Z]*+ keepend
syntax region elixirSigil start=+\~[a-zA-Z]'''+ end=+^\s*'''[a-zA-Z]*+ keepend
syntax keyword elixirTodo TODO FIXME XXX contained
syntax match elixirComment "#.*$" contains=elixirTodo
syntax sync minlines=100
highlight default link elixirKeyword Keyword
highlight default link elixirBoolean Boolean
highlight default link elixirOperator Operator
highlight default link elixirNumber Number
highlight default link elixirModule Type
highlight default link elixirAttribute PreProc
highlight default link elixirAtom Constant
highlight default link elixirKey Identifier
highlight default link elixirDefine Keyword
highlight default link elixirFunction Function
highlight default link elixirString String
highlight default link elixirSigil String
highlight default link elixirComment Comment
highlight default link elixirTodo Todo
let b:current_syntax = 'elixir'
