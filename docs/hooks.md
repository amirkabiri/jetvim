# Save hooks and annotations

Put extensions in user settings or trusted project settings (`⌘,`). Project
`hooks.after_save` replaces the user list; `after_save = {}` disables inherited
hooks. Existing project Lua only runs after `:JetvimTrustProject`.

```lua
return {
  hooks = {
    -- Optional fallback directories, relative to this project.
    tool_paths = { 'packages/tooling/.bin' },
    after_save = {
      {
        name = 'format',
        pattern = [[\.(js|jsx|ts|tsx)$]],
        workspace = true,
        command = { 'project-formatter', '--write', '{file}' },
      },
      {
        name = 'oxlint',
        pattern = [[\.(js|jsx|ts|tsx)$]],
        workspace = true,
        declared = true,
        command = { 'oxlint', '--format', 'json', '{file}' },
        diagnostics = 'oxlint',
      },
      {
        name = 'eslint',
        pattern = [[\.(js|jsx|ts|tsx)$]],
        workspace = true,
        declared = true,
        command = { 'eslint', '--format', 'json', '{file}' },
        diagnostics = 'eslint',
        timeout_ms = 10000,
      },
    },
  },
  git = { blame = { enabled = true, mode = 'current_line' } },
}
```

Patterns use Vim's **very magic** regex syntax. Commands run asynchronously in
project order. Ordinary hooks run from the project directory. `{file}` and `{project}` are replaced
inside individual arguments; shell operators are not interpreted. Required tools
must already be installed. Hooks run on manual saves and autosaves. Repeated
saves coalesce while a job runs. Formatters reload clean buffers; edits typed
while a formatter runs are preserved, and autosave pauses on external changes.
The timeout defaults to 10 seconds (maximum 120 seconds).

`workspace = true` runs from the closest ancestor `package.json` directory,
bounded by the selected project. It uses the nearest installed
`node_modules/.bin` tool, then the optional `hooks.tool_paths` directories. It
never downloads tools or falls back to a globally installed executable. `project-formatter`
follows the closest package's declared Prettier or Oxfmt formatter. It inspects
`format`/`lint:format` scripts and local package-script aliases without running
them. If there is no declaration, it checks the nearest formatter configuration,
then ancestor package scripts. Conflicting declarations/configurations warn
instead of guessing. Only the saved file is formatted; script globs and commands
are never executed. Use `prettier` or `oxfmt` directly to select one explicitly. A
project `tool_paths` list replaces the user list; `{}` clears inherited paths.

With `declared = true`, a linter runs only when the closest package's
`lint`/`lint:*` scripts declare that tool. Package-manager aliases and
`run-p`/`run-s`/`npm-run-all` aliases are inspected, never executed. A package
that declares only ESLint does not inherit Oxlint from the root. If it has no
lint scripts, ancestor package declarations are considered. Packages declaring
both tools receive both sets of diagnostics. Omit `declared` for an explicit
hook that should run regardless of package scripts.

Workspace ESLint uses the nearest `eslint.config.js/mjs/cjs`, legacy
`.eslintrc*`, or package `eslintConfig`, with the corresponding flat/legacy mode.
It honors an explicit `--config` argument. Files without a project-bounded
configuration are skipped and their previous hook diagnostics cleared. Ordinary
hooks without `workspace = true` retain their existing command behavior.

ESLint and Oxlint JSON findings appear as editor diagnostics, including left signs and the
right overview. Exit 1 means findings; other failures show a warning. Newer edits
invalidate pending results. Give hooks unique, stable `name` values.

A custom `diagnostics` function receives `(stdout, result, context)` and returns
entries with one-based `line`, `column` (UTF-8 bytes), `message`, `severity`
(`error`, `warn`, `info`, `hint`), and optional `code`. `context` contains `file`
and `buffer`. The ESLint parser converts its UTF-16 columns automatically. Oxlint columns
are already UTF-8 bytes; relative filenames resolve from the job directory.
Custom parser `context.cwd` contains that directory.

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
