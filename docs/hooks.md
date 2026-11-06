# Save hooks and annotations

Put extensions in user settings or trusted project settings (`⌘,`). Project
`hooks.after_save` replaces the user list; `after_save = {}` disables inherited
hooks. Existing project Lua only runs after `:JetvimTrustProject`.

```lua
return {
  hooks = {
    after_save = {
      {
        name = 'format',
        pattern = [[\.(js|jsx|ts|tsx)$]],
        command = { 'npx', '--no-install', 'prettier', '--write', '{file}' },
      },
      {
        name = 'eslint',
        pattern = [[\.js$]],
        command = { 'npx', '--no-install', 'eslint', '--format', 'json', '{file}' },
        diagnostics = 'eslint',
        timeout_ms = 10000,
      },
    },
  },
  git = { blame = { enabled = true, mode = 'current_line' } },
}
```

Patterns use Vim's **very magic** regex syntax. Commands run asynchronously in
project order, from the project directory. `{file}` and `{project}` are replaced
inside individual arguments; shell operators are not interpreted. Required tools
must already be installed. Hooks run on manual saves and autosaves. Repeated
saves coalesce while a job runs. Formatters reload clean buffers; edits typed
while a formatter runs are preserved, and autosave pauses on external changes.
The timeout defaults to 10 seconds (maximum 120 seconds).

ESLint JSON findings appear as editor diagnostics, including left signs and the
right overview. Exit 1 means findings; other failures show a warning. Newer edits
invalidate pending results. Give hooks unique, stable `name` values.

A custom `diagnostics` function receives `(stdout, result, context)` and returns
entries with one-based `line`, `column` (UTF-8 bytes), `message`, `severity`
(`error`, `warn`, `info`, `hint`), and optional `code`. `context` contains `file`
and `buffer`. The ESLint parser converts its UTF-16 columns automatically.

Extensions can publish independently:

```lua
local editor = require('jetvim.api')
editor.diagnostics('my-tool', buffer, {
  { line = 12, column = 3, severity = 'warn', message = 'Check this value' },
})
editor.annotations('my-tool', buffer, {
  { line = 12, text = 'A gray note' },
})
-- Pass {} to clear a source's diagnostics or annotations.
```

Git blame is on by default for the current line; set `enabled = false` to disable it. Set `mode = 'all'` for every line, or
`'current_line'` for the cursor line. Gray annotations show author and commit
summary, without email addresses. Unsaved lines show “Uncommitted changes”.
`:JetvimBlameInfo` shows the full commit hash, author, date and summary.
Blame uses cached read-only queries; moving the cursor does not launch Git.
