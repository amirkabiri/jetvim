# Jetvim shortcuts

macOS JetBrains bindings. Available in typing, selection, and Vim normal mode.

Terminal interception can prevent any application from receiving a shortcut.
Warp: see `terminal/warp.md`; other terminal adapters live in `terminal/`.

Escape enters Vim mode. Fallbacks are typed in normal mode: press Escape,
then Space followed by the displayed key. `Space Space` searches files and actions.

| Action | macOS shortcut | Normal-mode fallback | iTerm2: Send Escape Sequence |
| --- | --- | --- | --- |
| Project tool window | ⌘1 | Space 1 | `[983041u` |
| Go to File | ⌘⇧O | Space f | `[983042u` |
| Go to Class | ⌘O | Space c | `[983043u` |
| Go to Symbol | ⌘⌥O | Space y | `[983044u` |
| Find Action | ⌘⇧A | Space a | `[983045u` |
| Search Everywhere (terminal alternative) | ⌘⇧P | Space Space  | `[983046u` |
| Recent Files | ⌘E | Space e | `[983047u` |
| Recent Locations | ⌘⇧E | Space j | `[983048u` |
| Go to Line / Column | ⌘L | Space l | `[983049u` |
| Find | ⌘F | Space / | `[983050u` |
| Find Next | ⌘G | — | `[983051u` |
| Find Previous | ⌘⇧G | — | `[983052u` |
| Replace in File | ⌘R | Space r | `[983053u` |
| Find in Files | ⌘⇧F | Space g | `[983054u` |
| Save All | ⌘S | Space s | `[983055u` |
| Close Editor | ⌘W | Space w | `[983056u` |
| Undo | ⌘Z | — | `[983057u` |
| Redo | ⌘⇧Z | — | `[983058u` |
| Copy Selection or Line | ⌘C | — | `[983059u` |
| Cut Selection or Line | ⌘X | — | `[983060u` |
| Paste | ⌘V | — | `[983061u` |
| Paste from History | ⌘⇧V | — | `[983062u` |
| Select All | ⌘A | — | `[983063u` |
| Duplicate Selection or Line | ⌘D | Space d | `[983064u` |
| Delete Line | ⌘Backspace | — | `[983065u` |
| Toggle Line Comment | ⌘/ | Space /c | `[983066u` |
| Move Line Up | ⌥⇧↑ | — | `[983067u` |
| Move Line Down | ⌥⇧↓ | — | `[983068u` |
| Join Lines | ⌃⇧J | — | `[983069u` |
| Split Line | ⌘Enter | — | `[983070u` |
| Start New Line | ⇧Enter | — | `[983071u` |
| Extend Selection | ⌥↑ | — | `[983072u` |
| Shrink Selection | ⌥↓ | — | `[983073u` |
| Previous Word | ⌥← | — | `[983074u` |
| Next Word | ⌥→ | — | `[983075u` |
| Line Start | ⌘← | — | `[983076u` |
| Line End | ⌘→ | — | `[983077u` |
| File Start | ⌘↑ | — | `[983078u` |
| File End | ⌘↓ | — | `[983079u` |
| Select Previous Word | ⌥⇧← | — | `[983080u` |
| Select Next Word | ⌥⇧→ | — | `[983081u` |
| Select to Line Start | ⌘⇧← | — | `[983082u` |
| Select to Line End | ⌘⇧→ | — | `[983083u` |
| Select to File Start | ⌘⇧↑ | — | `[983084u` |
| Select to File End | ⌘⇧↓ | — | `[983085u` |
| Delete Previous Word | ⌥Backspace | — | `[983086u` |
| Delete Next Word | ⌥Delete | — | `[983087u` |
| Next Editor | ⌃→ | Space ] | `[983088u` |
| Previous Editor | ⌃← | Space [ | `[983089u` |
| Navigate Back | ⌘⌥← | Space b | `[983090u` |
| Navigate Forward | ⌘⌥→ | Space n | `[983091u` |
| Last Edit Location | ⌘⇧Backspace | — | `[983092u` |
| Code Block Start | ⌘⌥[ | — | `[983093u` |
| Code Block End | ⌘⌥] | — | `[983094u` |
| Select File in Project | ⌥F1 | — | `[983095u` |
| File Structure | ⌘F12 | Space o | `[983096u` |
| Go to Declaration | ⌘B | Space gd | `[983097u` |
| Go to Implementation | ⌘⌥B | Space gi | `[983098u` |
| Go to Type Declaration | ⌃⇧B | — | `[983099u` |
| Find Usages | ⌥F7 | Space gu | `[983100u` |
| Quick Documentation | ⌘J | Space k | `[983101u` |
| Parameter Info | ⌘P | — | `[983102u` |
| Rename Symbol | ⇧F6 | Space rn | `[983103u` |
| Intentions / Quick Fix | ⌥Enter | Space q | `[983104u` |
| Reformat Code | ⌘⌥L | Space = | `[983105u` |
| Optimize Imports | ⌃⌥O | — | `[983106u` |
| Code Completion | ⌃Space | — | `[983107u` |
| Call Hierarchy | ⌃⌥H | — | `[983108u` |
| Next Error | F2 | — | `[983109u` |
| Previous Error | ⇧F2 | — | `[983110u` |
| Error Description | ⌘F1 | — | `[983111u` |
| Expand Fold | ⌘+ | — | `[983112u` |
| Collapse Fold | ⌘− | — | `[983113u` |
| Expand All Folds | ⌘⇧+ | — | `[983114u` |
| Collapse All Folds | ⌘⇧− | — | `[983115u` |
| Terminal Tool Window | ⌥F12 | Space t | `[983116u` |
| Focus Editor | F4 | — | `[983117u` |
| Hide Tool Window | ⇧Escape | — | `[983118u` |
| Jetvim Settings | ⌘, | — | `[983119u` |
| Jetvim Shortcut Guide | ⌘? (Jetvim) | Space ? | `[983120u` |
| Git Changes | ⌘9 | Space 9 | `[983121u` |
| Stretch Pane Left | ⌃⌥← | — | `[983122u` |
| Stretch Pane Right | ⌃⌥→ | — | `[983123u` |
| Stretch Pane Up | ⌃⌥↑ | — | `[983124u` |
| Stretch Pane Down | ⌃⌥↓ | — | `[983125u` |
| Next Editor | ⌘⇧] | Space ] | `[983088u` |
| Previous Editor | ⌘⇧[ | Space [ | `[983089u` |

Double Shift is available with the optional Warp bridge. Else use ⌘⇧P or Space Space.
Search Everywhere currently searches project files and actions.
Language-aware navigation, completion and refactoring require an enabled LSP server.
⌥↑ expands through installed syntax nodes or enclosing code-block boundaries; ⌥↓ reverses each step.
The parserless fallback handles delimiters, strings/comments, Lua blocks and Python/YAML indentation;
ambiguous language constructs may differ from JetBrains semantic selection.
Project sidebar: type to search visible entries; arrows move through matches, Backspace edits,
Escape clears the query before returning to the editor. Plain letter keys are search text.
Left collapses a folder or selects its parent; Right expands it or enters its first child.
The project root is selectable. Drag the sidebar divider to resize it.
Ctrl+Option+Arrow resizes the focused pane by moving its shared divider in that direction.
For a left sidebar, Right grows and Left shrinks; for a bottom pane, Up grows and Down shrinks.
Resize steps are four columns or two rows; dimensions stop at ten columns or three rows.
Git Changes (⌘9): arrows select, Enter opens, Tab focuses the diff, R refreshes,
Escape focuses the editor and Shift-Escape hides the tool window. Diffs are read-only.
These are implemented bindings, not a claim of complete IntelliJ feature parity.
