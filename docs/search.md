# Find

**⌘F** opens a one-row search field at the top of the active editor. Matches
highlight as you type. Enter moves forward, Shift-Enter moves backward, and
Escape closes the field, clears highlights and returns to the selected match. **⌘G / ⌘⇧G** also
navigate matches, including after the field closes.

Plain text such as `hello world` is literal and case-insensitive. Wrap a pattern
in slashes, such as `/h(ello|i)/`, to use Vim's very-magic regular expressions.
Regex is case-sensitive; add `i` (`/hello/i`) to ignore case. Invalid expressions
appear in the field's status without opening an error dialog.

Search stops at 5,000 matches or 2 MiB of text; `+` beside the match count marks
that limit. The field follows the active editor's width and preserves pane sizes.

## Find in Files

**⌘⇧F** immediately opens a focused search modal. In the project tree it searches
within the selected folder, or a selected file's parent; selecting the root
searches the whole project. From the editor it searches the whole project.
The modal displays its scope above the input.

Plain text is literal and case-insensitive, searched after a 200 ms pause.
Use `/pattern/` for case-sensitive ripgrep regex or `/pattern/i` to ignore case.
Find in Files uses ripgrep's regex syntax; in-file Find uses Vim's very-magic syntax.
Up/Down choose results;
Shift+Up/Down or Shift+PageUp/PageDown selects a range. Enter opens each selected
file once at its first selected match; Escape cancels and restores focus.
Changing the query cancels the previous search. Errors appear inside the modal.
The input opens even without ripgrep; searching requires `rg`.

Search respects ignore files and skips `.git`, `.jetvim`, `.idea`, `node_modules`
and files over 2 MiB. Results stop at 500 matching lines (100 per file) and each
search times out after 10 seconds. A `+` marks capped results. Paths escaping the
project, including folder symlinks pointing outside it, cannot become search scopes.
