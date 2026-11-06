# External file changes

Jetvim checks loaded files every half second and when returning to a file or the
terminal window. Clean files reload after external edits, `git restore`, or
atomic file replacement. Cursor and scroll position remain where possible;
syntax, language servers, Git markers and blame refresh with the new contents.
Old save-hook diagnostics are cleared; language servers publish fresh results.

Unsaved edits are kept. A warning identifies a disk conflict; review both versions
before saving explicitly or reloading with `:edit!` (which discards local edits).
Deleted files keep their editor contents, and recreating a clean file reloads it.
Disk reloads do not run after-save hooks or write files.
