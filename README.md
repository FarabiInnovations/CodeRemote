# CodeRemote
Remotely start and control Claude Code and Codex sessions on your own machine.

## Run it

```bash
uv sync
uv run coderemote            # listens on 127.0.0.1:8765
```

It prints a link with an access token (`http://127.0.0.1:8765/#token=…`). Open it and the
page shows which platform you're on and whether Claude Code and Codex are ready for remote
control. The token is stored in `~/.config/coderemote/token` (macOS: `~/Library/Application
Support/coderemote`, Windows: `%APPDATA%\coderemote`).

Options: `--host` / `CODEREMOTE_HOST`, `--port` / `CODEREMOTE_PORT`. It only listens on this
machine by default. To reach it from your phone, put it behind a VPN such as Tailscale
rather than exposing it to the internet.

## Tests

```bash
uv run pytest
```
