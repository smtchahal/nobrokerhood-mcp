# nobrokerhood-mcp

A CLI and [MCP](https://modelcontextprotocol.io) server for pre-approving deliveries and visitors at your gate via the [NoBrokerHood](https://www.nobrokerhood.com) resident app — so you (or an LLM on your behalf) can say "let the Zepto guy in" instead of opening the app.

This is an unofficial client. It is not affiliated with or endorsed by NoBrokerHood.

## Install

```bash
pip install git+https://github.com/smtchahal/nobrokerhood-mcp.git
```

(Not yet published to PyPI.)

## Authentication

There's no OAuth flow — the client authenticates the same way the mobile app does, with a captured session. Proxy the NoBrokerHood app once (e.g. with [mitmproxy](https://mitmproxy.org/) or Charles Proxy) and pull the following out of a request:

- `NBH_USER_ID`, `NBH_SOCIETY_ID`, `NBH_DEVICE_ID` — from the `userId` / `societyId` / `deviceId` request headers
- `NBH_REMEMBER_ME`, `NBH_JSESSIONID` — from the `remember-me` / `JSESSIONID` cookies

Copy [`.env.example`](.env.example) to `.env` and fill these in (or export them directly — the client reads plain environment variables, nothing loads `.env` for you).

These sessions are long-lived but not eternal; if you start getting auth errors, recapture them.

## CLI usage

```bash
nbh pre-approve zepto --apartment-id <id>
nbh pre-approve dominos --apartment-id <id> --hours 4
nbh pre-approve amazon --apartment-id <id> --out "25/04/2026 23:59" --vehicle TWO_WHEELER
nbh cancel <visit-id> --apartment-id <id>
nbh list --apartment-id <id>
nbh visits --apartment-id <id>
nbh user-info
```

Run `nbh <command> --help` for the full flag list. `~100` delivery brands (Zepto, Blinkit, Swiggy, Dominos, Amazon, couriers, home services, ...) have built-in default approval windows — see `nobrokerhood.companies.KNOWN_COMPANIES`. Unknown brands default to a 1-hour window.

## MCP server

Registers six tools: `pre_approve`, `cancel_visit`, `list_expected`, `list_visits`, `get_user_multiprofile_info`, `known_companies`.

Add to your MCP client config (e.g. `.mcp.json` for Claude Code):

```json
{
  "mcpServers": {
    "nobrokerhood": {
      "command": "nobrokerhood-mcp",
      "env": {
        "NBH_USER_ID": "...",
        "NBH_SOCIETY_ID": "...",
        "NBH_DEVICE_ID": "...",
        "NBH_REMEMBER_ME": "...",
        "NBH_JSESSIONID": "..."
      }
    }
  }
}
```

This runs the server over stdio with no authorization layer — appropriate for local use, where the MCP client is the only thing that can spawn the process.

### Self-hosting over HTTP

If you want to expose this server remotely (e.g. behind a tunnel, for use from claude.ai instead of a local client), `nobrokerhood.server` exposes a `build_server()` factory instead of a fixed server instance, so you can bring your own authorization:

```python
from nobrokerhood.server import build_server

mcp = build_server(
    host="0.0.0.0",
    port=8000,
    streamable_http_path="/mcp",
    token_verifier=my_token_verifier,  # implement mcp.server.auth.provider.TokenVerifier
    auth=my_auth_settings,  # mcp.server.auth.settings.AuthSettings
)
mcp.run(transport="streamable-http")
```

This package intentionally does not ship an authorization implementation — how you authenticate callers to *your* server is a separate concern from how this client authenticates to NoBrokerHood.

## Library usage

```python
from nobrokerhood import NobrokerhoodClient

client = NobrokerhoodClient()  # reads NBH_* env vars
client.pre_approve("Zepto", apartment_id="...")
```

See `nobrokerhood/client.py` for the full API (`pre_approve`, `cancel_visit`, `list_expected`, `list_visits`, `register_device`, `get_user_multiprofile_info`, `get_home_content`).

## Development

```bash
pip install -e ".[dev]"
pre-commit install
pytest
```

## License

MIT — see [LICENSE](LICENSE).
