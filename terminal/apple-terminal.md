# Apple Terminal

Plain `jetvim` needs no Accessibility permission. Typing, mouse input and normal-mode
fallbacks work with ordinary terminal input: press Escape, then `Space 1` for the
tree, `Space f` for files or `Space ?` for shortcuts.

Apple Terminal reserves shortcuts such as ⌘N (new window) and ⌘W (close tab).
Its documented keyboard profiles customize function keys and Option-as-Meta;
full permissionless forwarding of JetBrains Command shortcuts is not verified.
See Apple's [Terminal shortcuts](https://support.apple.com/en-kw/guide/terminal/trmlshtcts)
and [custom function keys](https://support.apple.com/en-lamr/guide/terminal/trml108/mac).

For the optional macOS shortcut bridge, run in Apple Terminal:

```sh
jetvim --terminal-keys /path/to/project
```

It needs Python 3, the Swift compiler and macOS Accessibility authorization
(Device Control and Data Access on newer macOS versions). Use the helper path
printed by Jetvim when granting permission. No Terminal or system preferences
are changed by Jetvim.

The bridge intercepts mapped shortcuts only while **Apple Terminal** is frontmost
and its focused window's accessible title contains this Jetvim session's unique
token. Warp and other apps are excluded. Keep one bridged Jetvim session per
Terminal window; do not run separate bridges in tabs sharing the same window
title. macOS-reserved shortcuts can still take precedence.

For Jetvim installed inside an `sbx` container, leave its shell and run from the Mac:

```sh
jetvim --terminal-keys --sbx hacker
```

The helper stays on the Mac; Jetvim runs inside the container. Permissions,
physical shortcut interception and Apple Terminal's live title behavior require
manual verification; compiler and PTY tests do not establish those behaviors.
