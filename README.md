# CodeRemote
Remotely start and control Claude Code and Codex sessions on your own machine.

## Run it

```bash
uv sync
uv run coderemote            # listens on 127.0.0.1:8765
```

It prints a link with an access token (`http://127.0.0.1:8765/#token=…`). Open it and the
page shows which platform you're on and whether Claude Code and Codex are ready for remote
control. Below that you can browse the machine's folders, starting from your projects
folder. CodeRemote guesses it (e.g. `~/projects`, `~/code`, `~/src`) and falls back to your
home folder; open the right one and tap **Use as projects folder** to save it. The token is
stored in `~/.config/coderemote/token` (macOS: `~/Library/Application
Support/coderemote`, Windows: `%APPDATA%\coderemote`).

Pick a folder and tap **Start Claude here** or **Start Codex here**. CodeRemote starts
`claude remote-control` / `codex remote-control` in that folder, detached so it keeps running
if CodeRemote restarts, and shows whether it connected (with a link to the Claude session) or
why it failed. After that, the Claude app or the ChatGPT app takes over. The first time Claude
runs in a folder it has to be trusted; the page asks before it marks the folder as trusted in
`~/.claude.json`. Each launch keeps a small log (first 64 KB) in the settings folder's `logs/`.

Codex remote control also needs multi-factor authentication turned on for your ChatGPT account.

Options: `--host` / `CODEREMOTE_HOST`, `--port` / `CODEREMOTE_PORT`. It only listens on this
machine by default. To reach it from your phone, put it behind a VPN such as Tailscale
rather than exposing it to the internet.

## Tests

```bash
uv run pytest
```
