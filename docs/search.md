# Find

**⌘F** opens a one-row search field at the top of the active editor. Matches
highlight as you type. Enter moves forward, Shift-Enter moves backward, and
Escape closes the field and returns to the selected match. **⌘G / ⌘⇧G** also
navigate matches, including after the field closes.

Type `hello`, `h(ello|i)` or `/hello/i`. Search uses Vim's very-magic regular
expressions, one line at a time. The optional `i` flag ignores case; without it,
matching is case-sensitive. Invalid expressions appear in the field's status
without opening an error dialog.

Search stops at 5,000 matches or 2 MiB of text; `+` beside the match count marks
that limit. The field follows the active editor's width and preserves pane sizes.

**⌘⇧F** opens Find in Files from either the editor or the project sidebar,
including during sidebar speed search. The prompt opens even without ripgrep;
executing a project search requires `rg`.
