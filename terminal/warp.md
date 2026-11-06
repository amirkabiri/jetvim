# Warp setup

Start installed Jetvim with `jetvim`, or use `./jetvim` from a source checkout.
Jetvim uses Neovim's native support for
extended terminal keys. [Warp documents Kitty keyboard protocol support](https://docs.warp.dev/terminal/more-features/full-screen-apps),
but [Warp's key forwarding issue](https://github.com/warpdotdev/warp/issues/14300)
also records versions that consume Command shortcuts or lack configurable
send-text actions. Your installed version and its keybindings determine what
reaches Jetvim. The editor cannot recover a key that Warp has consumed. In a container or remote
shell, run plain `jetvim` there; shortcut handling still depends on the host
terminal forwarding the keys.

## Optional macOS bridge

```sh
./jetvim --warp-keys
```

The bridge requires Python 3 and the Swift compiler. The wrapper builds
`macos/KeyBridge.swift` into `$JETVIM_HOME/bin/keybridge`, then starts Neovim
inside a private PTY. The helper translates the configured macOS shortcuts
directly into that PTY. It does not synthesize global keyboard events.

The default installed helper is `~/.jetvim/bin/keybridge`; development checkouts
use `.jetvim/bin/keybridge` inside the checkout. Compiler module caches live in
`$JETVIM_HOME/cache/swift`. A custom `JETVIM_HOME` moves both locations.

macOS must authorize keyboard interception. If the helper reports missing
permission, open System Settings → Privacy & Security → **Device Control and Data
Access** on macOS 27 or later. On earlier macOS versions the permission is named
**Accessibility**. Enable Warp or the helper identified in the error, then retry.
If the helper is absent, click **+**, press **Command-Shift-G**, and enter its
full path, for example:

```text
~/.jetvim/bin/keybridge
```

Use the actual helper path printed in the error for a development checkout or
custom runtime location. Then rerun `jetvim --warp-keys` (or `./jetvim --warp-keys`
from source). Depending on
macOS policy, Input Monitoring may also be necessary. Jetvim neither requests
permissions automatically nor changes those settings.

The newer permission name is documented in
[Symless's macOS permission guide](https://support.symless.com/hc/en-us/articles/35743428145169-Troubleshooting-the-macOS-Device-Control-and-Data-Access-or-Accessibility-permission).

The helper only intercepts a binding when:

- Warp is the frontmost app (bundle identifier begins with `dev.warp.`).
- The focused accessible Warp window title contains the unique title of this
  Jetvim session, for example `Jetvim-12ab34cd`.
- The key exactly matches a configured Jetvim shortcut.

All other key events pass through. Double Shift opens Search Everywhere.
On quitting, the helper exits and the PTY wrapper restores terminal input modes.

The bridge also forwards **Fn+Shift+Up/Down** as Shift-PageUp/Down and
**Fn+Shift+Left/Right** as Shift-Home/End. This bypasses Warp bindings that consume
those combinations. These native navigation sequences go only to this Jetvim
session's private PTY; existing shortcut relay IDs stay unchanged. Ordinary
Shift-arrows retain their normal behavior. Restart `jetvim --warp-keys` after
updating the bridge. Physical Fn forwarding still needs a live Warp check.

The initial bridge uses physical US keyboard positions. Other layouts need a
layout-aware translator. A Warp window must expose its active session's terminal
title to macOS Accessibility. If Warp keeps a custom window title or exposes a
different title, the bridge deliberately passes keys through. It does not guess
which window to control. This title behavior and the OS permission flow require
manual testing in your Warp session.

macOS-reserved shortcuts, including Mission Control bindings, can still take
precedence. The bridge does not change system shortcuts. Do not enable two
bridges in panes sharing the same window title: use one Jetvim session per Warp
window until pane-aware focus detection is implemented.

## Check the received key

Inside Jetvim, press Escape and run `:JetvimKeyCheck`, then press a shortcut.
Jetvim reports the key representation Neovim receives. For example, a native
Command-S should be `<D-s>`; a bridge key is a private Unicode character.
If Warp performs its own action and Jetvim receives nothing, use the optional
bridge or the documented normal-mode fallback.

No Warp config file has been installed or modified. A generated iTerm2 preset
and Ghostty adapter are available alongside this document for later testing.
