# Jetvim task tracker

The lead owns version control, task coordination, independent validation and commits.
Implementation agents must not run Git commands or create commits.
All development changes and test fixtures stay inside this checkout.
A later explicit request authorizes changes only to one external project’s Jetvim settings; its source and audit artifacts are not committed here.

Statuses distinguish committed/pushed work, independently validated changes awaiting commit, active fixes, and unverified platform checks.

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
| Close all tabs without changing sidebar/editor geometry | layout_fix agent | Independently validated: 64 live PTY checks | Repeated Command-W cannot delete tool panes; preserve custom sidebar width and empty editor slot; reopen from tree/picker without extra splits; unsaved cancel preserves layout |
| Toggle the project tree with Command-1 | layout_fix agent | Independently validated in layout suite | Show/focus when hidden or inactive; hide when already focused; restore chosen width and stable editor slot |
| Resize panes with keyboard shortcuts | resize_keys agent | Independently validated: 57 checks | Control-Option-arrows match macOS JetBrains resize bindings; preserve existing Control-arrow tab navigation, focus/mode and safe minimum pane sizes |
| Per-line Git markers in the left editor gutter | git_gutter agent | Committed/pushed `dfc19a7`; 35 real Git + 51 mocked checks on staged snapshot | Blue modified lines, green added lines, red deletion anchors; unsaved buffer versus HEAD; coexist with diagnostics; no Git/index/worktree mutations |
| Configurable debounce/focus-leave autosave and immediate Command-S | hooks_bridge agent | Independently validated: 33 new-spec checks; committed `540ff33` | Default 1-second debounce; typing resets timer; independently toggle debounce and file/sidebar focus-leave saves; configurable delay; manual save always available; preserve Discard/readonly/external-change safety |
| Remember every tool pane across toggles/restarts | autosave_settings agent + dispatcher fix public_ci | Independently validated: 35 live PTY/persistence checks; committed `540ff33` | Preserve user height through hide/show and terminal exit/recreate; clamp to host terminal; native/relay shortcut tests |
| Remember resized Git tool-window dimensions | git_gutter agent (Git pane lifecycle) | Independently validated: 25 live PTY checks; committed `540ff33` | Preserve bottom height and list/diff split width through Command-9 hide/show; clamp to terminal dimensions without capturing teardown-expanded geometry |
| Diagnostic overview markers on the right of the editor | layout_fix agent (overview module) | Independently validated: 37 TUI/mouse checks | Red errors, yellow warnings, distinct info/hints scaled over the whole file at the right edge; update with diagnostics and do not alter pane layout |
| Go server enabled but declaration action unavailable | go_lsp agent | Independently validated: 21 real Go LSP checks | Preserve enabled Go config; local-only binary/build/module/cache paths and telemetry-off environment; actual Go Command-B definition test |
| User/project Lua settings, project overrides and trust | autosave_settings agent | Independently validated: 39 checks; committed `540ff33` | User settings outside source; empty project return table; project overrides only specified fields; unknown project Lua requires trust |
| Save hooks, formatters and ESLint diagnostics bridge | hooks_bridge agent | Independently validated: 34 async hook/API checks; committed `540ff33` | Safe argv commands; regex file matching; stale-result protection; formatter preserves edits; line diagnostics reach editor and overview |
| Native GitToolBox-style gray Git blame annotations | hooks_bridge agent | Independently validated: 10 real Git + 4 insert-mode PTY checks | Read-only cached blame; current-line/all modes; no emails by default; independently validated real Git fixture |
| Inline regex search on Command-F | public_ci agent | Committed/pushed `a8fb834`; 31 checks on exact staged snapshot | Top editor search bar; hello and /hello/i patterns; next/previous matches; invalid regex handled inline |
| Folder-scoped Find in Files modal on Command-Shift-F | public_ci agent | Committed/pushed `e5ae01f`; 46 modal + 31 search checks | Native and relay shortcuts open a focused floating search modal; selected folder scopes results; async cancellation and safe paths |
| One-command macOS/Linux installation | installer agent | Committed/pushed `c54b122`; 9 offline tests, real Git update smoke, all 4 macOS ARM assets verified | Clone under ~/.jetvim/code; preserve user settings; verified dependencies; isolated install/update tests; honest terminal limitations |
| Short README and combined IDE/Vim logo | public_ci agent | Committed/pushed `d0372f8`; lead inspected rendered SVG | Exact introduction: Imagine if JetBrains and Vim had a baby!; one install command; local original logo |
| GitHub Actions tests and packages | public_ci agent | Configured/pushed; local checks pass; hosted results not verified without GitHub API/browser access | macOS/Linux matrix; pinned actions; tests and privacy audit; no private runtime artifacts |
| Public source and history privacy review | Lead + public_ci agent | Complete: all 7 historical commits sanitized and main replaced with approved force-with-lease; source/history scans pass | No confidential data; no personal machine paths; exclude caches/settings; no license per user request |
| Option-Delete deletes previous word in embedded terminal | public_ci agent | Independently validated: 27 native/relay byte + real Bash checks; committed `540ff33` | Native127/8 CSI-u, legacy Escape-Delete and relay each send one Ctrl-W; physical Warp right-Option still requires live user verification |
| Reload externally changed files, including git restore | disk_sync agent | Committed/pushed `b0b2c1a`; 57 checks including real Git restore | Clean named buffers reload automatically; preserve views and unsaved edits; refresh Git indicators; handle atomic replacements/deletion/recreation |
| Short workspace-aware formatter/linter hooks | hooks_bridge + project_hooks agents | Committed/pushed `dc0d0c8`; 49 workspace + 21 actual autosave pipeline checks | Native local-tool/config discovery; short user/project Lua settings; preserve argv/cwd/ESLint diagnostics; no dependency downloads |
| Configure an existing project with its installed formatter/linter | project_hooks agent | Settings updated: declared formatter → Oxlint/ESLint where declared; native Oxlint support committed/pushed `cf5252f` | Modify only explicitly authorized project settings; use installed tools and correct workspace configurations; validate read-only |
| Create files/folders using Command-N in the tree | public_ci agent | Committed/pushed `ebfb767`; 37 creation checks, 88 bridge shortcuts validated | Native/relay prompt, selected directory, exclusive file creation, nested folders, cancel and path guards |
| Configure the project lint chain, including Oxlint | hooks_bridge + project_hooks agents | Committed/pushed `cf5252f`; 36 parser/pipeline checks plus actual installed Oxlint on an isolated fixture | Respect declared Oxlint/ESLint scripts; parse Oxlint JSON into line diagnostics; retain complementary checks and ESLint-only workspaces |
| Clear in-file search highlights when closing search | public_ci agent | Committed/pushed `00d6a09`; 45 PTY/rendering checks | Clear native and custom highlights on Escape; preserve last query and Command-G navigation |
| Respect the declared project formatter on save | hooks_bridge + project_hooks agents | Committed/pushed `dc0d0c8`; actual target-file Oxfmt/config checks passed read-only | Inspect scripts/configs without running scripts; local binaries only; one saved file; ambiguity reported |
| Show diagnostics while typing and preserve Git signs with multiple linters | public_ci agent | Committed/pushed `cf5252f`; 21 live TUI + 35 real Git gutter checks | Updates in insert mode; two Git signs plus highest diagnostic coexist in three slots; cursor/focus unchanged |
| Option-Delete in the folder-search modal | public_ci agent | Committed/pushed `b34f2ce`; 118 independent PTY checks | Both Option key encodings delete a word without leaving the search input; plain Backspace still deletes one character |
| Right Arrow from Local Changes list focuses its diff pane | git_diff_focus agent | Committed/pushed `b3a333a`; 36 focus + 48 real Git checks passed | Native arrow from a selected file focuses its existing diff, preserves selection and sizes, and remains safe for empty/non-repositories |
| Extend selection with Fn-Shift-arrows | shift_page_selection + fn_bridge agents | Committed/pushed `db78ead` | 110 native PTY checks, 31 paging checks and 57 Swift routing cases; optional bridge needs live Warp verification |
| Collapse Select All to the file start with Up Arrow | shift_page_selection agent | Committed/pushed `db78ead` | Command-A from EOF then Up reaches first line; 230 structural, 118 input-deletion and 38 integration checks passed in isolated CI settings |
| Preserve structural selection history through autosave | shift_page_selection agent | Committed/pushed `d451281` | 264 independent checks with autosave enabled; unchanged text preserves history, real edits invalidate it |
| Command-B on a definition lists usages | definition_usages agent | Complete; independently validated | 43 terminal-input checks, 17 actual TypeScript and 21 actual Go checks; usage picker, Unicode, save-only changes and stale responses verified |
| Fix Ubuntu CI Git-cache render assertion | vcs_ci_failure agent | Committed/pushed `be49923`; Ubuntu x86/ARM and macOS ARM CI passed | Isolate unrelated blame/gutter providers; full Git suite passed (48 changes, 29 filename colors, 35 gutter, 10 blame, 57 disk checks); direct/deferred render Git fault injections still fail |
| Fix macOS CI autosave timing assertion | autosave_ci_failure agent | Committed/pushed `1605187`; Ubuntu x86/ARM and macOS ARM CI passed | 37 real PTY checks passed normally and with 400ms host pause; incorrect 1ms delay and missing debounce reset both rejected; product code unchanged |
| Forward Warp shortcuts into sbx Docker/Linux | sbx_shortcuts agent | Optional bridge implemented and independently validated; live container check pending | Five portable test methods verify literal argv, both app targets, key transport, resize, exit and terminal restoration; native input remains permissionless |
| Fix Intel macOS project-search cancellation test | search_ci_failure agent | Committed/pushed `08c1091`; independently validated; GitHub rerun pending | 48 checks pass with deliberate 1s host pause; missing cancellation and appended stale results both rejected by fault injections |
| Apple Terminal shortcut support | terminal_native_keys + sbx_shortcuts agents | Optional bridge implemented and independently validated; full native Command forwarding unverified | Compiled helper passes 20 focus cases, 88 shortcut mappings and 57 Fn routes; 5 Terminal tests pass; Accessibility and physical focus behavior need user verification |
| Commit/push completed tasks after independent validation | Lead | Active policy; search, gutter, installer and editor bundle committed/pushed | Review code and exact staged functionality, run relevant tests, commit and push without agent Git access |
| Initialize Git, validate delegated changes, then commit | Lead | Complete: implementation committed as `c4db90e` after independent validation | Independently inspect diffs and run required tests before committing |
| Support additional terminals over time | Future terminal adapters | Backlog | Shared actions; terminal-specific forwarding and focus validation |
| Complete JetBrains navigation/editing feature parity | Future iterations | Partial implementation | Remaining capabilities documented in README; no blanket parity claim |

No completed feature is considered validated solely because an agent reports success.
The lead records exact validation results and commit references below after review.

Initial implementation validation (historical milestone):

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

Implementation milestone: `c4db90e` — Build Jetvim with macOS JetBrains navigation
and project tools. The lead created this commit; agents created no commits and ran
no Git commands. This tracker update records the completed validation milestone.

Validated task commits pushed by the lead: `a8fb834` (search), `dfc19a7` (Git gutter), `c54b122` (installer and Go tooling). Each isolated staged snapshot passed its relevant tests before committing.

Current validation milestone (`540ff33`):

- Full core suite passed with pinned Neovim 0.12.6, including settings 39,
  hooks 34, autosave 33, search 31, terminal keys 27, persistent panes 35,
  resize 57, editor layout 64, overview 37 and all existing editor suites.
- Real Git group passed: changes 48, filename colors 28, gutter 35 and blame 10.
- Isolated installer snapshot passed 9 tests, TypeScript 14 and Go 21 checks.
- Real shallow clone/two-commit fast-forward preserved settings and refused dirty
  source updates. All four macOS ARM upstream archives passed SHA-256 and binary
  execution checks. Linux and Intel execution are assigned to hosted CI.
- Swift bridge compiled and `--check-keymap` validated 87 physical shortcuts.
- Physical Warp keyboard forwarding remains a user-side check. No terminal or
  operating-system settings were changed during development.

Privacy cleanup completed with explicit user approval: sanitized `main` was pushed using a lease against the reviewed prior tip. All seven rewritten commits passed source-pattern scans and use public noreply attribution. The product code at the reviewed tip is unchanged. Original review artifacts remain local under ignored runtime storage.

Latest task validation:

- `b0b2c1a`: all core checks and the real Git group passed against an isolated
  staged snapshot, including disk reload/restore and formatter/linter pipelines.
  The validation copy was shortened after hitting the macOS socket pathname limit.
- `e5ae01f`: 46 project-search modal checks and the 31-check in-file search suite
  passed; the lead inspected the actual floating-window grid rendering.
- Project formatter selection passed 49 checks. Actual autosave → formatter →
  ESLint passed 21 PTY checks; the shared autosave suite still passes 33.
- Read-only validation of the separately authorized project confirmed the two
  reported source files select Oxfmt and its real configuration; synthetic stdin
  formatting left those files unchanged. Existing explicit Prettier workspaces
  retain their formatter. Ambiguous declarations produce a diagnostic notice.
- Hook-only fixtures exclude unrelated language servers and capture failure
  state without increasing their deadlines. Private project config and audit
  artifacts are not included in this repository or release archive.

Current follow-up validation:

- Search-close cleanup is committed/pushed as `00d6a09` after 45 checks.
- Oxlint parsing is independently validated with 36 cases and actual installed
  Oxlint JSON from a generated fixture; no real external-project source was linted.
- Live diagnostics and multi-provider Git sign coexistence passed 21 rendering
  checks and the 35-check real Git gutter suite. Committed/pushed as `cf5252f`.
- Option-Delete’s latest report concerns the folder-search input, distinct from
  the already-validated embedded-terminal transport. The popup fix is committed as `b34f2ce` after 118 independent checks.

Git pane navigation: `b3a333a` passed 36 focused PTY checks, including stale callbacks and diff reading-position preservation, plus the existing 48 real Git checks. The lead owns the commit; the agent ran no Git commands.
