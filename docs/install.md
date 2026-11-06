# Install

```bash
curl -fsSL https://raw.githubusercontent.com/amirkabiri/jetvim/main/install.sh | bash
```

Requires Git, curl, tar and a SHA-256 utility. Supports macOS and glibc Linux on Apple Silicon/ARM64 and Intel/AMD64. The installer clones `~/.jetvim/code`, keeps your Lua settings at `~/.jetvim/settings.lua`, and installs tools/cache separately under `~/.jetvim`. Rerun the command to update; your settings remain untouched. Code updates require a clean checkout and fast-forward history.

Compatible Neovim, ripgrep, Node and Go already on PATH are reused. Missing tools are installed locally from pinned official archives with SHA-256 verification. Default setup includes TypeScript and Go language tools. No sudo, fonts, terminal settings or shell profiles are changed.

Run `jetvim [folder]`. The installer links it into a writable standard bin directory already on PATH when possible, otherwise `~/.local/bin`. If needed, add that directory to PATH using the printed instruction. `⌘,` opens Lua settings; trusted project overrides live in `.idea/jetvim/settings.lua`.

Terminal Vim shortcuts work across terminals. Exact Command-key shortcuts depend on terminal support; the macOS Warp bridge requires Accessibility permission. See [shortcuts and setup](guide.md).

For custom locations, set `JETVIM_HOME` and `JETVIM_BIN_DIR`. For a core-only setup, set `JETVIM_SKIP_LANGUAGES=1`. CI can set `JETVIM_SOURCE_DIR` to an existing source checkout to bootstrap tools without cloning. Set all these paths inside the checkout when developing. The installed code and each tool retain their upstream licensing terms.
