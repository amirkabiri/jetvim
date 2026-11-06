# Embedded terminal keys

Option + the macOS Delete/Backspace key sends one `Ctrl+W` to the shell, deleting
the preceding word. Native Alt-Backspace, Alt-CtrlH and the Jetvim terminal relay
use the same mapping. Left and right Option have the same meaning when the
terminal forwards their Alt modifier. Unmodified spaces and Backspace keep their
ordinary meaning; `Ctrl+W` is also available directly.

Shortcuts received together keep their order: opening the terminal and resizing
it in one input batch resizes the terminal pane.

In Warp, use `jetvim --warp-keys` if an Option key arrives as ordinary text or
Backspace instead of Alt-Backspace. The optional macOS bridge recognizes both
physical Option keys through the same Alt modifier. It requires the permissions
in the [Warp guide](../terminal/warp.md); physical key behavior still needs
verification in your live Warp session.
