# Create files and folders

Focus the project tree and press **⌘N** or Insert. Enter a relative filename;
append `/` to create a folder. Nested paths work too. Creation uses the selected
folder, or the parent of the selected file.

Files are created empty on disk and opened in the editor. Folders are revealed
and selected in the sidebar. Escape cancels. Existing files are never overwritten,
and paths escaping the project, including through symlinks, are rejected.

⌘N works through native terminal keys or the generated terminal relay. Warp users
can use `jetvim --warp-keys` when Warp consumes the shortcut. The action applies
only to the project tree; it does not insert text into editors or embedded shells.
