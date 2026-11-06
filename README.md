# Jetvim

A Neovim-based terminal editor for people with macOS JetBrains muscle memory.
The first version includes a project sidebar, fuzzy file/action search, ordinary
typing and selection, Vim mode, Git change previews, and macOS JetBrains
navigation/editing/tool actions.

## Start

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

The bridge requires Swift to build and macOS Device Control and Data Access
authorization (named Accessibility on older macOS versions) to run.
Read [the Warp setup guide](terminal/warp.md) before enabling it. It has not been
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

The [full shortcut guide](docs/shortcuts.md) lists every implemented binding.
All provided navigation and editing bindings use the macOS JetBrains convention.
Jetvim-specific help uses ⌘?; Search Everywhere uses ⌘⇧P when a terminal cannot
report Double Shift. The Warp bridge also recognizes Double Shift.

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
resize the sidebar with the mouse. Searching, refreshing and refocusing retain
that width while the sidebar stays open.

Plain keys, including `a`, `r`, `l`, Space and `:`, are search text in the
sidebar. Exit to the editor before using Vim command-line or Space-prefixed
fallback shortcuts. Insert creates a file/directory (a trailing `/` creates a
directory), and F5 refreshes the tree. Native ⌘N also opens the creation prompt
when the terminal forwards it; the Warp bridge does not currently map ⌘N.
Filenames are passed as data, so spaces and special characters work.

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

- **Warp:** [setup and restrictions](terminal/warp.md).
- **Ghostty:** generated [dedicated-window configuration](terminal/ghostty.conf).
  Launch a separate instance/window with that config; don't apply it globally to
  unrelated shells. See [Ghostty's keybinding documentation](https://ghostty.org/docs/config/keybind).
- **iTerm2:** import [Jetvim.itermkeymap](terminal/Jetvim.itermkeymap) under a
  dedicated profile's Keys → Key Mappings → Presets/Import. This is a preset to
  review, not an automatically installed configuration. The shortcut guide also
  lists each literal **Send Escape Sequence** value for manual setup. See
  [iTerm2's key mapping documentation](https://iterm2.com/documentation-preferences-profiles-keys.html).
- **Apple Terminal and other terminals:** use native keys where supported and the
  normal-mode fallbacks. Additional terminal adapters can be added to `scripts/generate.py`.

## Language features

Basic editing, file navigation, project search, comments, undo, selection and the
sidebar work without a server. Declaration, class/symbol search, completion,
rename, usages, quick fixes and formatting need a compatible language server.

Edit [config/lsp.lua](config/lsp.lua) to configure installed language servers.
Examples for Go, Python and TypeScript are provided. Startup never downloads
language tools. Enabling a server in the configuration starts the installed
server for matching filetypes; the current saved configuration has `ts_ls`
enabled. Server capabilities and any files they create are controlled by those
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

Configuration,
generated profiles, caches, undo files, test fixtures, logs, temporary files and
the optional bridge binary stay under this directory. It does not read your
personal Neovim init file or load your personal Neovim plugins. Ordinary Neovim
file writes outside the selected project or Jetvim's own directory are rejected,
including paths through symlinks.
This is a file-write guard, not a security sandbox for shell commands or plugins.

`config/keymap.json` is the shared shortcut registry. Editor mappings, terminal
adapters and documentation derive from it. After changing it:

```sh
python3 scripts/generate.py
python3 scripts/generate.py --check
JETVIM_DISABLE_VCS=1 python3 tests/integration.py
JETVIM_DISABLE_VCS=1 python3 tests/tui.py
JETVIM_DISABLE_VCS=1 python3 tests/launcher.py
JETVIM_DISABLE_VCS=1 python3 tests/sidebar.py
JETVIM_DISABLE_VCS=1 python3 tests/selection.py
JETVIM_DISABLE_VCS=1 python3 tests/tabs.py
JETVIM_DISABLE_VCS=1 python3 tests/appearance.py
JETVIM_DISABLE_VCS=1 python3 tests/paging.py
python3 tests/vcs_cache.py
```

The VCS opt-out prevents background Git processes during implementation-agent
checks. The cache suite mocks the process API. Per [AGENTS.md](AGENTS.md), only
the lead runs the real-Git suites; they create isolated repositories inside
`.jetvim/`:

```sh
python3 tests/git_changes.py
python3 tests/vcs.py
```

After installing the optional TypeScript tools, verify actual language-server
attachment and Go to Declaration with:

```sh
JETVIM_DISABLE_VCS=1 python3 tests/lsp.py
```

The integration test drives a real Neovim process and input event loop. It checks
editing in typing/selection/normal modes, navigation, tree focus, search pickers,
terminal relay mappings, file saving and path boundaries. It does not prove that
a particular terminal forwards physical key events or that an LSP server works.

Shortcut reference: [JetBrains macOS keymap](https://resources.jetbrains.com/storage/products/intellij-idea/docs/IntelliJIDEA_ReferenceCard.pdf).
Terminal input reference: [Neovim TUI documentation](https://neovim.io/doc/user/tui/).
