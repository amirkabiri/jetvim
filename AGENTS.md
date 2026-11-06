# Jetvim working agreement

- Keep development changes, generated artifacts, test repositories, logs, caches
  and temporary files inside this checkout. Do not modify shell, terminal or
  system settings outside it.
- The lead tracks requests in `TASKS.md`, coordinates implementation agents,
  independently reviews and validates their work, and owns commits.
- Delegate product implementation to agents. Give each agent explicit file
  ownership and coordinate shared-file changes before editing.
- Implementation agents must not run Git commands or change `.git`, including
  when preparing test fixtures. They may author Git-related tests; the lead runs
  those tests and manages the project repository.
- Treat agent reports as claims to verify. Inspect the resulting code and tests,
  run the relevant checks independently, and resolve material failures before
  committing. Do not commit merely because an agent says tests passed.
- Exclude `.jetvim/`, `.idea/` and generated runtime/compiler state from commits.
  Do not commit unrelated user files.
- Keep the shared keymap, terminal adapters and shortcut documentation consistent.
  Verify actual terminal input as well as direct Neovim action calls for shortcuts.
- Preserve the macOS bridge's restriction to the focused, identified Jetvim
  session. Permission grants and live Warp focus behavior require user-side
  verification; do not claim those were tested by a compiler or PTY test.
