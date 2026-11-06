# Settings

Press `⌘,` and choose **User settings** (`~/.jetvim/settings.lua`) or
**Project settings** (`.idea/jetvim/settings.lua`). These are ordinary Lua files.
Save to apply; invalid settings keep the last working configuration.

Installed defaults → user settings → trusted project overrides. New project
settings contain only `return {}`. Existing project Lua requires
`:JetvimTrustProject` before it executes; use `:JetvimUntrustProject` to revoke.

```lua
return {
  autosave = {
    enabled = true,
    debounce = true,
    delay_ms = 1000,
    on_focus_lost = true,
  },
}
```

These are the defaults. Typing restarts the idle timer: the file saves one second
after the last edit. Leaving the file for another file or a tool such as the
sidebar also saves. Moving between splits showing the same file does not.

Set `debounce = false` to disable idle saves, or `on_focus_lost = false` to disable
leave saves. Each works independently. `enabled = false` disables both.
`delay_ms` accepts 100–60000 milliseconds. `⌘S` always saves immediately,
regardless of automatic-save settings.

A project can override one field without copying the rest:

```lua
return { autosave = { on_focus_lost = false } }
```

Autosave skips unnamed, readonly and tool buffers. It preserves newer edits when
a file changes outside the editor, waits for running save hooks, and never
interferes with an explicit Discard choice. Failed writes leave the buffer dirty
and show a warning. Review conflicting disk changes before saving explicitly.

See [save hooks and annotations](hooks.md) for formatters, ESLint and Git blame.
