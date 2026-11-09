# Jetvim

A Neovim-based terminal editor for people with macOS JetBrains muscle memory.
The first version includes a project sidebar, fuzzy file/action search, ordinary
typing and selection, Vim mode, Git change previews, and macOS JetBrains
navigation/editing/tool actions.

## Install and start

Install with the command in the [README](../README.md). The installer keeps source,
tools and personal preferences under `~/.jetvim`; it does not change terminal
preferences. Read [installation details](install.md) for updates and prerequisites.
Run `jetvim /path/to/project` after installation.

For development from a source checkout:

Neovim 0.11+ is required. Normal startup installs no plugins, package managers,
language servers or terminal settings. Optional local TypeScript tooling can be
installed explicitly using the setup script described below.
Ripgrep (`rg`) enables Find in Files; file browsing also has a built-in fallback.

From this directory:

```sh
./jetvim
./jetvim README.md
./jetvim /path/to/project
./jetvim --warp-keys /path/to/project
```

Start typing immediately when a file is open. Escape enters Vim normal mode;
`i` returns to typing. Shift + arrows selects text, and typing replaces a selection.
The welcome screen is read-only: open a file using the tree or Go to File.

**Warp users:** start with `./jetvim`. Native Command mappings work only if your
Warp version forwards those keys. If Warp consumes them, the optional, local macOS
bridge is available with:

```sh
./jetvim --warp-keys
```

The bridge requires Python 3, the Swift compiler, and macOS Device Control and
Data Access authorization (named Accessibility on older macOS versions) to run.
Read [the Warp setup guide](../terminal/warp.md) before enabling it. It has not been
verified against your live Warp session. It never changes Warp preferences.

## Familiar shortcuts

| Action | macOS JetBrains key |
| --- | --- |
| Project sidebar | ⌘1 |
| Go to File / Class / Symbol | ⌘⇧O / ⌘O / ⌘⌥O |
| Find Action | ⌘⇧A |
| Recent Files / Locations | ⌘E / ⌘⇧E |
| Go to Line | ⌘L |
| Navigate Back / Forward | ⌘⌥← / ⌘⌥→ |
| Previous / Next editor | ⌘⇧[ / ⌘⇧] (also ⌃← / ⌃→) |
| Find / Find in Files / Replace | ⌘F / ⌘⇧F / ⌘R |
| Save All / Close Editor | ⌘S / ⌘W |
| Copy / Cut / Paste | ⌘C / ⌘X / ⌘V |
| Undo / Redo | ⌘Z / ⌘⇧Z |
| Duplicate / Delete line | ⌘D / ⌘Backspace |
| Comment | ⌘/ |
| Move line | ⌥⇧↑ / ⌥⇧↓ |
| Extend / Shrink selection | ⌥↑ / ⌥↓ |
| Declaration / Implementation / Usages | ⌘B / ⌘⌥B / ⌥F7 |
| Rename / Quick Fix / Format | ⇧F6 / ⌥Enter / ⌘⌥L |
| Terminal | ⌥F12 |
| Git Changes | ⌘9 |

On macOS, Fn+↑ / Fn+↓ sends Page Up / Page Down. Jetvim pages by the visible
editor text height minus two lines, and reaches the first/last line even when the
remaining distance is less than one page. Paging preserves the preferred column
and keeps typing mode active when invoked while editing.
Add Shift to Fn+↑/↓ (Shift+PageUp/PageDown) to extend the selection by a page.
The anchor stays fixed when repeating or reversing direction. Fn+Shift+←/→
(Shift+Home/End) selects to the current line’s start/end. With a typing selection,
plain Up/Left collapses to its start and Down/Right to its end; explicit Vim
Visual mode continues to extend using ordinary arrows.

The [full shortcut guide](shortcuts.md) lists every implemented binding.
All provided navigation and editing bindings use the macOS JetBrains convention.
Jetvim-specific help uses ⌘?; Search Everywhere uses ⌘⇧P when a terminal cannot
report Double Shift. The Warp bridge also recognizes Double Shift.
Go to File and Search Everywhere accept pasted `path:line[:column]` references,
including quoted paths; line and column numbers start at 1.

Without any terminal setup, press Escape followed by:

| Keys in Vim normal mode | Action |
| --- | --- |
| Space 1 | Project tree |
| Space 9 | Git Changes |
| Space f | Go to File |
| Space a | Find Action |
| Space Space | Search files and actions |
| Space e | Recent Files |
| Space g | Find in Files |
| Space s | Save All |
| Space ? | Shortcut guide |

Picker controls: type to filter, ↑/↓ to choose, Enter to open, Escape to cancel.

The Project sidebar uses Speed Search: focus it with ⌘1 and start typing a file
or folder name. Matching visible entries are highlighted without changing the
tree hierarchy; ↑/↓ moves through the matches. Matching is case-insensitive and
supports fuzzy names, spaces and Unicode text. Backspace removes the last
character. The first Escape clears an active query and keeps sidebar focus;
Escape with no query returns to the editor. Enter opens a matching file or
toggles a matching directory, while ←/→ collapses/expands it. Search includes
expanded descendants; use Go to File (⌘⇧O) to search the whole project.
Right on an expanded folder enters its first child; Left on a file or collapsed
folder selects its parent. Moving to a parent/child that does not match the active
query dismisses that query. The project root is selectable too: a second Left on
a closed top-level folder selects the root. The root can be collapsed/expanded;
↑/↓ skips the search header. Drag the divider between the sidebar and editor to
resize the sidebar with the mouse. Its width is remembered across toggles and
restarts; searching, refreshing and refocusing preserve it too.

Plain keys, including `a`, `r`, `l`, Space and `:`, are search text in the
sidebar. Exit to the editor before using Vim command-line or Space-prefixed
fallback shortcuts. Insert creates a file/directory (a trailing `/` creates a
directory), and F5 refreshes the tree. **⌘N** opens the same prompt through
native terminal input or the Warp bridge. It acts only while the tree is focused.
Creation uses the selected folder or the selected file’s parent, creates the disk
entry immediately, and never overwrites an existing path.
Filenames are passed as data, so spaces and special characters work.
**⌘Delete** (the Mac Backspace key) deletes the selected file/folder after a
permanent-deletion confirmation. Native ⌘Forward Delete works too. Dirty files
and running save hooks block deletion; symbolic links are unlinked without
touching their targets. In the editor, ⌘Backspace still deletes a line.
**Shift+F6** renames the selected tree file/folder in its current directory.
Open files keep their edits and follow the new path; existing names are never overwritten.
Resolve disk conflicts and finish active save hooks before renaming.
In an editor, Shift+F6 continues to rename a code symbol through its language server.

**⌘⌥F1** (or ⌥F1) reveals the current file and opens its path menu.
Choose Copy Relative Path or Copy Absolute Path; Escape closes the menu and keeps tree focus.

## Resize panes with the keyboard

Use **Ctrl+Option+←/→/↑/↓** to move a shared divider toward the requested
direction. These follow JetBrains' macOS tool-window resize bindings;
Ctrl+←/→ remains available for editor-tab navigation.

For the left sidebar, Right grows it and Left shrinks it. For a bottom tool
window, Up grows it and Down shrinks it. An editor or middle pane can grow
toward a neighboring pane on either side. At an outside edge, the available
divider moves in that direction instead, shrinking the focused pane.

Each press moves four columns or two rows, stopping before a neighboring or
focused pane becomes narrower than ten columns or shorter than three rows.
Focus, the editing mode, and terminal input mode are preserved. Resizing does
nothing on an axis without a shared divider or inside a floating dialog.
The native terminal keys and the Warp bridge both support these bindings.

## Appearance

The WebStorm-inspired dark palette uses muted separators, blue selections,
a tab strip and file-type colors. The tree and editor
tabs use file/folder icons. Filename labels also show Git status: modified tracked
files are blue, and untracked files are red. File-type icons keep their own colors.
Git status is cached asynchronously and refreshed on saves, terminal focus and
sidebar focus/refresh; drawing the tree or tab strip never waits for Git.
`config/appearance.lua` defaults to
`icons = 'portable'`, which uses Unicode and short text labels without requiring
an installed icon font. If your terminal already uses a Nerd Font, change that
setting to `icons = 'nerd'` and restart Jetvim for the glyph variant. Jetvim does
not install fonts or change your terminal's font settings.

## Expand selection

Press ⌥↑ repeatedly to expand an identifier into enclosing expressions, strings,
code blocks/functions and eventually the buffer. ⌥↓ reverses those expansion
steps and restores the original caret. The history belongs to the current buffer
and resets after edits, filetype changes or a different manual selection.

Jetvim uses installed Tree-sitter syntax nodes when available and never downloads
parsers. Without a parser, a structural fallback recognizes matching `()`, `[]`
and `{}`, quoted strings/comments, common JavaScript regexes, Lua `end` blocks and
long strings, and Python/YAML indentation blocks. It selects complete nested
objects in JSONL instead of adding unrelated lines above and below the selection.
The fallback is based on text and indentation, so ambiguous constructs such as
JavaScript template interpolation or regex-versus-division syntax and unusual raw
literals can differ from JetBrains semantic selection.

## Git Changes

Press ⌘9 (or Escape, then Space 9) to open the bottom Git Changes tool window.
The left pane groups conflicts, staged changes, unstaged changes and untracked
files. Selecting a file shows its read-only unified diff in the right pane;
staged and unstaged versions of the same file appear separately. The tool does
not stage files, commit, discard edits, or change Git configuration.

Use ↑/↓ to select a changed file and Enter to open it in the editor. Tab focuses
the diff, and Shift-Tab returns to the list. `R` refreshes the changes; saving a
file also refreshes an open panel. Escape returns focus to the editor, while
Shift-Escape hides the panel. Pressing ⌘9 while the panel is focused toggles it
closed. A folder outside a Git repository shows an explanatory message.
In the file list, ⌘A selects all change entries and shows their count. Ordinary
arrows clear the selection; Enter still opens only the focused file.
Tool-pane sizes persist per project in `.idea/jetvim/layout.json`: project-tree
width, Git panel height and change-list width, and terminal panel height. Mouse
and Ctrl+Option+Arrow resizing are remembered across toggles and restarts. Layout
metadata is created after a manual resize. Smaller terminals clamp restored
panes to fit while retaining preferred sizes for a larger terminal. Editors use
the remaining space.
In the embedded terminal, ⌘V pastes clipboard text while keeping terminal input
active; multiline paste honors the child shell’s bracketed-paste support.

## Git line markers

The editor's **left gutter**, beside the line numbers, shows changes against the
last committed version (`HEAD`): blue bars for modified lines, green bars for
added lines, and red triangles at deleted-line positions. Deletions at the start
or end of a file are anchored to the nearest remaining line; deleting all text
leaves a red marker on the empty first line. New untracked text files have green
line markers even though their filenames are red in the tree.

The comparison includes unsaved edits and staged plus unstaged changes together.
Reverting a change removes its marker. Three fixed left-side sign slots let
overlapping modification/deletion markers and diagnostics remain visible.
Typing diffs a cached baseline in memory; Git is refreshed asynchronously on file
entry, save, focus, or status refresh. Ignored files, non-repositories, binary
content and text over 5 MiB are skipped. Gutter reads never stage or write files.

## Terminal compatibility

There are two paths from a physical key to an editor action:

1. Extended keyboard reporting: Jetvim accepts native Command/Option/Control keys
   through Neovim's terminal keyboard support.
2. Adapters: terminals that consume keys can send a distinct sequence for each
   action. The Warp bridge, Ghostty configuration, and iTerm2 preset all use the
   same action registry and transport sequences.

Terminal compatibility is ongoing work. Exact shortcuts cannot be guaranteed in
every terminal: a terminal or macOS may reserve a chord before Jetvim sees it.
Fallbacks and Find Action remain available. macOS Mission Control commonly
reserves Control + arrows; those system shortcuts may need to be reassigned by
the user for a terminal to receive them. No system settings are changed here.

- **Warp:** [setup and restrictions](../terminal/warp.md).
- **Ghostty:** generated [dedicated-window configuration](../terminal/ghostty.conf).
  Launch a separate instance/window with that config; don't apply it globally to
  unrelated shells. See [Ghostty's keybinding documentation](https://ghostty.org/docs/config/keybind).
- **iTerm2:** import [Jetvim.itermkeymap](../terminal/Jetvim.itermkeymap) under a
  dedicated profile's Keys → Key Mappings → Presets/Import. This is a preset to
  review, not an automatically installed configuration. The shortcut guide also
  lists each literal **Send Escape Sequence** value for manual setup. See
  [iTerm2's key mapping documentation](https://iterm2.com/documentation-preferences-profiles-keys.html).
- **Apple Terminal:** native keys and normal-mode fallbacks need no permission;
  the optional `jetvim --terminal-keys` bridge supports scoped Command shortcuts.
  See [setup, permissions and limitations](../terminal/apple-terminal.md).
- **Other terminals:** use native keys where supported and normal-mode fallbacks.
  Additional terminal adapters can be added to `scripts/generate.py`.

## Find in the current file

**⌘F** opens a one-row search field at the top of the active editor. Matches
highlight as you type. Enter goes forward; Shift-Enter goes backward; Escape
closes the field and returns to the editor. **⌘G / ⌘⇧G** continue the search.

Plain text such as `hello world` is literal and case-insensitive. Use `/h(ello|i)/`
for a case-sensitive Vim very-magic regex, or `/hello/i` to ignore case. Invalid
patterns appear in the bar without an error dialog. Search is per line, with a 5,000-match / 2 MiB limit
indicated by `+`. **⌘⇧F** opens a focused Find in Files modal. In the tree it
searches the selected folder or file’s parent; selecting the root searches the
whole project. The modal displays its scope and searches literal text without
case sensitivity. Use `/pattern/` for case-sensitive ripgrep regex, or `/pattern/i`
to ignore case.
Shift+↑/↓ selects a result range; Shift+PageUp/PageDown (Fn+Shift+↑/↓ on macOS)
extends it by a page. Plain arrows collapse the range; Enter opens each selected
file once at its first selected match.
See [search behavior and limits](search.md).

## Settings and autosave

Press **⌘,** to choose Project settings, User settings, Appearance or LSP under separate headings.
Appearance and LSP changes apply after restarting Jetvim.
Defaults in `config/settings.lua` are overlaid by `~/.jetvim/settings.lua`, then
`.idea/jetvim/settings.lua` in the selected project. Development checkouts use
`.jetvim/settings.lua` for user settings. Project files are sparse overrides:

```lua
return { autosave = { enabled = false } }
```

This disables autosave for one project while inheriting the user's other values.
Autosave starts enabled with a one-second debounce and a save when leaving a file
for another file or the sidebar. Set `autosave.debounce = false` or
`autosave.on_focus_lost = false` independently. `autosave.enabled = false` disables
both; **⌘S** always saves manually. `autosave.delay_ms` accepts 100–60000
milliseconds and defaults to 1000. See [autosave settings](settings.md).
Saving applies valid changes immediately; invalid code or values retain the
last working settings. Jetvim preserves your comments and unknown extension keys.
`:JetvimUserSettings` and `:JetvimProjectSettings` open each scope directly;
`:JetvimReloadSettings` reloads external edits.

Existing project Lua runs only after `:JetvimTrustProject`; revoke with
`:JetvimUntrustProject`. A new empty project settings file deliberately created
through Jetvim is trusted. Opening an existing file does not grant trust.

Autosave writes only named, editable files inside the selected project or
Jetvim's own directory. It skips unnamed, read-only, sidebar, preview and tool
buffers. External disk changes and write failures pause autosave for that file
while preserving its unsaved contents. Explicit Discard during close takes
precedence over any pending autosave. **⌘S** still saves all files manually.

Language-server and appearance settings remain in `config/lsp.lua` and
`config/appearance.lua` respectively. The scope chooser opens code; preferences remain Lua files.

## Save hooks and annotations

Configure regex-matched after-save commands in Lua, including ESLint diagnostics
and external formatters. Extensions can publish diagnostics and line annotations.
Git blame appears in gray beside the current line; use `git.blame.mode = 'all'`
for all lines or `git.blame.enabled = false` to disable it.
See [hook, extension API and blame examples](hooks.md).

## Language features

Basic editing, file navigation, project search, comments, undo, selection and the
sidebar work without a server. Declaration, class/symbol search, completion,
rename, usages, quick fixes and formatting need a compatible language server.
Press `⌘B` on a reference to jump to its definition; on the definition, it opens a selectable usages list.
In the Usages picker, ⌘A selects all filtered results; Enter opens one tab per file, and editing the query clears the selection.

Edit [config/lsp.lua](../config/lsp.lua) to configure installed language servers.
Examples for Go, Python and TypeScript are provided. Startup never downloads
language tools. Enabling a server in the configuration starts the installed
server for matching filetypes; the current saved configuration has `ts_ls` and
`gopls` enabled. Server capabilities and any files they create are controlled by those
tools.

For JavaScript/TypeScript, install the optional server into this checkout:

```sh
./scripts/setup-typescript.sh
```

The setup requires an existing Node.js 22.22.2+ and npm. It installs pinned
`typescript-language-server@6.0.3` and `typescript@6.0.3`, keeping packages, npm
configuration and caches under `.jetvim/`. Restart Jetvim afterward. The enabled
`ts_ls` configuration is preserved; the launcher adds the local tools to PATH for
Jetvim only. No global packages or shell settings are changed.
`:JetvimLspInfo` reports the current filetype, attached servers and missing
executables. JSON/JSONL files need their own suitable JSON language-server
configuration; the TypeScript server does not attach to them.

For Go, install the optional server into this checkout:

```sh
./scripts/setup-gopls.sh
```

This requires Go 1.27+ and either Python 3 or Node.js; the installer supplies
Node when needed. It builds pinned `gopls@v0.24.0` from the official Go module
proxy, with one local source adjustment to send its telemetry API to a runtime
directory whose mode is `off`. Tools, module downloads, build caches, gopls caches
and temporary files stay under `JETVIM_HOME` (`~/.jetvim` when installed,
checkout-local `.jetvim/` in development).
Restart Jetvim afterward; its child process finds the local server without
changing your shell or global Go settings. Keep `gopls` enabled in
`config/lsp.lua` and open a Go project containing `go.mod` or `go.work`.
`:JetvimLspInfo` shows the attached server, executable, enabled configuration and
matching workspace root to diagnose Go to Declaration (`⌘B`).

This is a working foundation, not full IntelliJ parity. Debugging, run
configurations, structural refactoring, multiple cursors, project-wide replace
and semantic smart completion are not yet implemented. Search Everywhere
currently covers files and actions. Code folding uses indentation.

## Workspace and development

An initial directory argument selects the project for the sidebar, search and
file writes. Without one, Jetvim uses the shell's current directory. File arguments
after the project directory are relative to that project. For example:

```sh
jetvim --warp-keys /path/to/project src/main.go
```

To run `jetvim` from any directory, add this checkout to PATH for the current shell:

```sh
export PATH="/path/to/jetvim:$PATH"
```

For persistence, add that same line to your `~/.zshrc` yourself, then open a new
shell or run `source ~/.zshrc`. Jetvim does not edit shell configuration files.
The executable is named `jetvim` (not `jetbim`).

In development mode, configuration, generated profiles, caches, undo files, test
fixtures, logs, temporary files and the optional bridge binary stay under this
checkout. The installed launcher uses `~/.jetvim` for user settings and tools, and
project-local `.idea/jetvim` for editor state. It does not read your
personal Neovim init file or load your personal Neovim plugins. Ordinary Neovim
file writes outside the selected project or Jetvim's own directory are rejected,
including paths through symlinks.
This is a file-write guard, not a security sandbox for shell commands or plugins.

`config/keymap.json` is the shared shortcut registry. Editor mappings, terminal
adapters and documentation derive from it. After changing it:

```sh
python3 scripts/generate.py
python3 scripts/generate.py --check
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/integration.py
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/tui.py
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/launcher.py
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/sidebar.py
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/selection.py
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/tabs.py
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/appearance.py
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/paging.py
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/resize.py
python3 tests/vcs_cache.py
python3 tests/gutter_cache.py
python3 tests/autosave.py
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/git_layout.py
```

The VCS opt-out prevents background Git processes during implementation-agent
checks. The autosave opt-out keeps explicit unsaved-buffer assertions deterministic;
the dedicated autosave suite exercises the default enabled behavior with isolated
Lua settings inside `.jetvim/`. The cache suite mocks the process API. Per [AGENTS.md](../AGENTS.md), only
the lead runs the real-Git suites; they create isolated repositories inside
`.jetvim/`:

```sh
python3 tests/git_changes.py
python3 tests/vcs.py
python3 tests/git_gutter.py
```

After installing the optional TypeScript tools, verify actual language-server
attachment and Go to Declaration with:

```sh
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/lsp.py
```

After installing the optional Go tools, test real Go attachment and native
terminal `⌘B` input with:

```sh
JETVIM_DISABLE_VCS=1 JETVIM_DISABLE_AUTOSAVE=1 python3 tests/go_lsp.py
```

The integration test drives a real Neovim process and input event loop. It checks
editing in typing/selection/normal modes, navigation, tree focus, search pickers,
terminal relay mappings, file saving and path boundaries. It does not prove that
a particular terminal forwards physical key events or that an LSP server works.

Shortcut reference: [JetBrains macOS keymap](https://resources.jetbrains.com/storage/products/intellij-idea/docs/IntelliJIDEA_ReferenceCard.pdf).
Terminal input reference: [Neovim TUI documentation](https://neovim.io/doc/user/tui/).
