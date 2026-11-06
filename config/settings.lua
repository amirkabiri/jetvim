-- Jetvim settings. Open with ⌘, and save to apply changes immediately.
-- If a setting is invalid, Jetvim keeps the last working configuration.
-- Language servers: config/lsp.lua. Colors/icons: config/appearance.lua.
return {
  autosave = {
    enabled = true,
    debounce = true,
    on_focus_lost = true,
    -- Idle delay after the last edit, in milliseconds (100–60000).
    delay_ms = 1000,
  },
  git = {
    blame = {
      enabled = true,
      -- Gray annotations beside the current line; use 'all' for every line.
      mode = 'current_line',
    },
  },
}
