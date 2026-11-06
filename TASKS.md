# Jetvim task tracker

The lead owns version control, task coordination, independent validation and commits.
Implementation agents must not run Git commands or create commits.
All development changes and test fixtures stay inside this checkout.

| User request | Owner | Status | Acceptance checks |
| --- | --- | --- | --- |
| Neovim editor with macOS JetBrains bindings and a project sidebar | Lead (existing implementation) | Validated: editor, launcher and live TUI suites pass | Startup, editing, navigation, sidebar and real PTY input tests |
| Warp Command-key forwarding | Lead (existing implementation) | Bridge compiles; live OS permission/focus testing remains manual | Swift compilation, transport decoding; user verifies physical key interception |
| Clarify macOS permission names | Lead (existing implementation) | Updated and compiler-checked; OS grants remain user-controlled | Device Control and Data Access on macOS 27+, Accessibility on earlier versions |
| Open a selected project folder and run from PATH | Lead (existing implementation) | Independently validated by launcher suite | Explicit project, current directory, PATH, project writes and local runtime paths |
| Sidebar type-to-search | sidebar agent | Independently validated: 90 sidebar checks passed | Typed letters and Unicode, highlighting, match navigation, backspace, Escape, Enter and control-character filenames |
| Left on a closed tree folder selects its parent | sidebar agent | Independently validated in sidebar suite | Expanded → collapsed → parent, including a direct child of the selectable project root |
| Resize the sidebar with the mouse | sidebar agent | Independently validated in sidebar suite | Actual divider drag bytes; preserve width after search, refresh and focus changes |
| Expand/shrink selection by syntax and enclosing blocks | selection agent | Independently validated: 230 checks passed | Nested syntax/brace/indent blocks, compact JSONL, strict growth, exact shrinking, stale history and Unicode |
| Previous/next editor using Command-Shift-brackets | git_tabs agent | Independently validated: 29 checks passed | Both aliases in native terminal input and relay forwarding; skip terminal/tools and preserve typing mode |
| Git Changes panel on Command-9 | git_tabs agent | Independently validated: 48 real Git checks passed | Staged, unstaged, untracked, rename/delete, clean/non-repository, conflicts, pane lifecycle and unchanged index/worktree |
| Match WebStorm colors, icons and spacing | appearance agent + sidebar integration | Independently validated: 40 checks and visual inspection | Dark surfaces, blue active tab/selection, file icons without font installation, readable spacing and unchanged keyboard behavior |
| Git-status filename colors | sidebar provider/tree + appearance tabs; git_tabs authors lead-only Git tests | Independently validated: 28 real Git + 29 mocked cache checks | Modified tracked filenames blue; untracked filenames red in tree and editor tabs; icons retain type colors |
| Fn-Up/Down paging reaches file boundaries | selection paging module + git_tabs key integration | Independently validated: 31 checks passed | Native Page Up/Down bytes; page-sized movement clamped to first/last line, preferred column and typing mode preserved |
| TypeScript server enabled but declaration action unavailable | appearance agent (local setup) | Independently validated: 14 real server checks passed | Enabled config preserved; local server/TypeScript 6.0.3 installed; actual Command-B definition jump succeeds |
| Initialize Git, validate delegated changes, then commit | Lead | All required checks passed; implementation commit prepared | Independently inspect diffs and run required tests before committing |
| Support additional terminals over time | Future terminal adapters | Backlog | Shared actions; terminal-specific forwarding and focus validation |
| Complete JetBrains navigation/editing feature parity | Future iterations | Partial implementation | Remaining capabilities documented in README; no blanket parity claim |

No completed feature is considered validated solely because an agent reports success.
The lead records exact validation results and commit references below after review.

Independent final validation:

- `python3 tests/selection.py`: 230 structural selection checks passed.
- `python3 tests/integration.py`: 38 editor integration checks passed after all
  feature and TypeScript setup changes.
- `python3 tests/tabs.py`: 29 checks passed, including both native CSI-u bracket
  encodings, terminal routing, unsaved editors and typing-mode preservation.
- `python3 tests/sidebar.py`: 90 live PTY checks passed, including actual mouse
  divider dragging, closed-folder → parent/root navigation, status colors and
  startup/search/opening with CR/LF/tab characters in filenames.
- `python3 tests/paging.py`: 31 checks passed using actual Page Up/Down bytes.
- `python3 tests/appearance.py`: 40 checks passed; the lead also inspected the
  actual-cell PNG capture. Visual captures use mocked statuses; the real-Git
  color suite separately verifies the provider and rendered filename groups.
- `python3 tests/git_changes.py`: 48 checks passed against real repositories.
- `python3 tests/vcs.py`: 28 real Git filename-color checks passed.
- `python3 tests/vcs_cache.py`: 29 mocked cache/process checks passed.
- `python3 tests/lsp.py`: 14 checks passed with the locally installed TypeScript
  server, including attachment and Command-B navigation to another file.
- `python3 tests/launcher.py` and `python3 tests/tui.py`: passed.
- Generated adapters match the registry; shell/Python syntax and whitespace checks pass.
- Independently compiled the Swift bridge and safely validated 83 physical key
  mappings with `--check-keymap`, without starting keyboard interception.

Review findings corrected before commit included malformed test-driver escaping,
terminal startup emulation, shifted-brace native key encoding, stale selection
history, batched sidebar input invoking global shortcuts, and raw CR/LF/tab
filename labels blocking TUI startup. The lead reran the affected checks.

Live macOS permission grants and focused-Warp key interception remain manual
verification. Other terminals and complete IntelliJ feature parity remain backlog.
