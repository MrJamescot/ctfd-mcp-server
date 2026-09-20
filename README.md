# CTFd MCP Server

<!-- mcp-name: io.github.MrJamescot/ctfd-mcp-server -->

[![PyPI - Version](https://img.shields.io/pypi/v/ctfd-mcp-server.svg)](https://pypi.org/project/ctfd-mcp-server/)
[![PyPI - Python Versions](https://img.shields.io/pypi/pyversions/ctfd-mcp-server.svg)](https://pypi.org/project/ctfd-mcp-server/)
[![Docker Pulls](https://img.shields.io/docker/pulls/jamescot/ctfd-mcp-server.svg)](https://hub.docker.com/r/jamescot/ctfd-mcp-server)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/MrJamescot/ctfd-mcp-server?style=flat)](https://github.com/MrJamescot/ctfd-mcp-server)

A Model Context Protocol (MCP) server for interacting with any **CTFd v3** instance.
It lets AI tools (Claude Desktop, Cursor, custom agents, ...) authenticate, list
and inspect challenges, submit flags, and query instance state through a stable,
type-safe interface.

The project ships two interfaces built on the **same** client library:

- **MCP tools** (primary) — `ctfd_mcp_server.py`, used over `stdio` or `sse`.
- **REST API** (optional) — `server/main.py`, a FastAPI mirror for scripting,
  debugging, and Docker deployments.

```
                 ┌──────────────────────────────────────────────┐
 AI agent / MCP  │            FastMCP (MCP tools)               │
 client ────────►│  set_token · login · challenges · submit_flag │
                 └──────────────────┬───────────────────────────┘
                                    │  shared client
                 ┌──────────────────▼───────────────────────────┐
 curl / scripts ─►│  FastAPI REST (/api/v1/...)  (optional)      │
                 └──────────────────┬───────────────────────────┘
                                    │
                 ┌──────────────────▼───────────────────────────┐
                 │   server.ctfd_client.CTFdClient               │
                 │   └─ gateway.py  (HTTP, auth, timeouts)       │
                 └──────────────────┬───────────────────────────┘
                                    │ HTTPS / HTTP
                              ┌─────▼─────┐
                              │   CTFd    │
                              └───────────┘
```

Credentials (token / cookie / password) live **in memory only** and are never
echoed in tool output, written to `server_state.json`, or logged.

---

## Features

- **Multiple authentication modes** — API token, session cookie, or username/password
  form login (with CSRF handling).
- **Rich challenge queries** — paginated listing with `category`, `search` (name),
  and `solved`/`unsolved` filters, plus per-challenge detail retrieval.
- **Safe flag submission** — requires an explicit `confirm=True`, returns clear
  success/failure, and surfaces rate-limit errors. Flags are never logged.
- **Instance introspection** — public instance info, health check, and an
  authentication-status tool that reveal no secrets.
- **Consistent structured errors** — `AuthenticationError`, `CTFdAPIError`,
  `ChallengeNotFoundError`, `SubmissionError`, `ValidationError`,
  `ConfigurationError`.
- **Pagination by default** — one page of challenges per call; no accidental
  full-dump downloads.
- **Hardened HTTP** — configurable timeouts, one safe retry for idempotent `GET`s,
  no retries for `POST`s (no duplicate submissions), strict JSON/content parsing.
- **REST + MCP from one codebase** — identical behaviour on both interfaces.
- **No hardcoded instance** — `BASE_URL` is validated and configurable at startup
  and at runtime.

---

## Installation

Requires Python 3.10+.

The fastest way is to install from **[PyPI](https://pypi.org/project/ctfd-mcp-server/)**:

```bash
pip install ctfd-mcp-server

# MCP stdio server with env config:
CTFD_BASE_URL=https://ctf.example.com CTFD_ADMIN_TOKEN=ctfd_... ctfd-mcp

# optional REST interface:
ctfd-rest
```

For MCP clients, point your config at the packaged entry point:

```jsonc
{
  "mcpServers": {
    "ctfd-mcp": {
      "command": "ctfd-mcp",
      "env": {
        "CTFD_BASE_URL": "https://demo.ctfd.io",
        "CTFD_ADMIN_TOKEN": "ctfd_..."
      }
    }
  }
}
```

Or run from source:

```bash
git clone https://github.com/MrJamescot/ctfd-mcp-server.git
cd ctfd-mcp-server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env     # then edit .env
```

### Configure

| Variable               | Default               | Meaning                                        |
| ---------------------- | --------------------- | ---------------------------------------------- |
| `CTFD_BASE_URL`        | *(empty)*             | CTFd instance root, e.g. `https://ctf.example.com` (without `/api/v1`) |
| `CTFD_ADMIN_TOKEN`     | *(empty)*             | API token (preferred auth)                     |
| `CTFD_SESSION_COOKIE`  | *(empty)*             | Session cookie, e.g. `session=abc...`          |
| `CTFD_USERNAME`        | *(empty)*             | Username for form login                        |
| `CTFD_PASSWORD`        | *(empty)*             | Password for form login                        |
| `CTFD_HTTP_TIMEOUT`    | `15`                  | Per-request HTTP timeout (seconds)             |
| `CTFD_MCP_TRANSPORT`   | `stdio`               | MCP transport: `stdio` or `sse`                |
| `MCP_HOST` / `MCP_PORT`| `0.0.0.0` / `8000`    | REST server bind settings                      |
| `FILE_CACHE_DIR`       | `./file_cache`        | Where downloaded challenge files are stored    |
| `CTFD_PERSIST_SECRETS` | `false`               | ⚠ Strongly discouraged: write secrets to disk  |

> `CTFD_BASE_URL` may include a path prefix (e.g. `https://host/ctfd`); the client
> appends `/api/v1` automatically.

---

## Running the MCP Server

Most MCP clients launch the server themselves via a `command`/`args` config.
For that, your client config should reference **`ctfd_mcp_server.py`**:

```jsonc
// e.g. Claude Desktop / mcp.json
{
  "mcpServers": {
    "ctfd-mcp": {
      "command": "python",
      "args": ["/path/to/ctfd-mcp-server/ctfd_mcp_server.py"],
      "env": {
        "CTFD_BASE_URL": "https://demo.ctfd.io",
        "CTFD_ADMIN_TOKEN": "ctfd_..."
      }
    }
  }
}
```

Manual launch:

```bash
# stdio (default) — used by MCP clients
python ctfd_mcp_server.py

# SSE — expose over HTTP for remote/Docker use
CTFD_MCP_TRANSPORT=sse python ctfd_mcp_server.py   # http://127.0.0.1:8000/sse
```

### MCP tools

| Tool              | Parameters                                                              | Description |
| ----------------- | ----------------------------------------------------------------------- | ----------- |
| `set_base_url`    | `url`                                                                   | Point the server at a CTFd instance |
| `set_token`       | `token`                                                                 | Adopt an API token (memory only) |
| `set_cookie`      | `cookie`                                                                | Adopt a session cookie (memory only) |
| `login`           | `username`, `password`                                                  | Form login; keeps the session cookie |
| `challenges`      | `category`, `search`, `solved`, `page`, `per_page`                      | Paginated challenge list with filters |
| `challenge`       | `identifier` (id **or** name)                                           | Full detail of one challenge |
| `submit_flag`     | `flag`, `challenge_name`/`challenge_id`, `confirm`                      | Submit a flag (requires `confirm=True`) |
| `scoreboard`      | —                                                                       | Public scoreboard standings |
| `progress`        | —                                                                       | Your score + solved challenges |
| `instance_info`   | —                                                                       | Safe public instance metadata |
| `auth_status`     | —                                                                       | Auth mode + validity (no secrets) |
| `health`          | —                                                                       | Reachability, API and auth checks |
| `download_file`   | `file_id`                                                               | Save a challenge file to the cache |

Tools return JSON text. Errors are structured, e.g.:

```json
{ "error": { "type": "ChallengeNotFoundError", "message": "Challenge '99' not found (or not visible)." } }
```

---

## Running the REST API (optional)

```bash
python scripts/run_local.sh           # reads .env, default http://127.0.0.1:8000
# or
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

Endpoints (all under `/api/v1`):

| Method | Path                          | Description                              |
| ------ | ----------------------------- | ---------------------------------------- |
| POST   | `/set_base_url`               | Validate & set the CTFd base URL         |
| POST   | `/set_token`                  | Set API token                            |
| POST   | `/set_cookie`                 | Set session cookie                       |
| POST   | `/set_creds`                  | Store username/password for later login  |
| POST   | `/login`                      | Form login (session cookie)              |
| GET    | `/challenges`                 | Paginated + filtered challenge list      |
| GET    | `/challenges/{id-or-name}`    | Challenge detail                         |
| POST   | `/submit`                     | Submit a flag (`confirm: true` required) |
| GET    | `/scoreboard`                 | Public standings                         |
| GET    | `/progress`                   | Your score and solves                    |
| GET    | `/instance_info`              | Public instance metadata                 |
| GET    | `/auth_status`                | Auth mode + validity                     |
| GET    | `/health`                     | Health check                             |
| GET    | `/files/{fid}/download`       | Save a challenge file                    |

---

## Docker

A ready-made image is published on **[Docker Hub](https://hub.docker.com/r/jamescot/ctfd-mcp-server)**:

```bash
docker run --rm -p 8000:8000 \
  -e CTFD_BASE_URL=https://ctf.example.com \
  -e CTFD_ADMIN_TOKEN=ctfd_... \
  jamescot/ctfd-mcp-server
```

Or build locally (REST mode):

```bash
docker build -t ctfd-mcp .
docker run --rm -p 8000:8000 \
  -e CTFD_BASE_URL=https://ctf.example.com \
  -e CTFD_ADMIN_TOKEN=ctfd_... \
  ctfd-mcp
```

`docker compose up --build` also works (REST API on `http://localhost:8000`).

To run the **MCP SSE** server in a container instead:

```bash
docker run --rm -it -e CTFD_BASE_URL=https://ctf.example.com ctfd-mcp python ctfd_mcp_server.py
# stdio on the attached terminal
```

---

## Usage examples

### MCP (agent)

```
1. set_base_url      url="https://ctf.example.com"
2. set_token         token="ctfd_..."
3. challenges        category="web", solved=false, page=1, per_page=25
4. challenge         identifier="3"
5. submit_flag       flag="flag{...}", challenge_id=3, confirm=true
```

### REST

```bash
curl -X POST http://localhost:8000/api/v1/set_base_url \
  -H 'Content-Type: application/json' -d '{"url":"https://ctf.example.com"}'

curl -X POST http://localhost:8000/api/v1/set_token \
  -H 'Content-Type: application/json' -d '{"token":"ctfd_..."}'

curl 'http://localhost:8000/api/v1/challenges?search=web&solved=false&per_page=10'

curl -X POST http://localhost:8000/api/v1/submit \
  -H 'Content-Type: application/json' \
  -d '{"challenge_id":3,"flag":"flag{...}","confirm":true}'

curl http://localhost:8000/api/v1/health
```

See [`DEMO.md`](DEMO.md) for a complete walkthrough and
[`examples/`](examples) for curl and Python snippets.

---

## Development & testing

```bash
pip install -r requirements-dev.txt

python -m pytest -q          # 76 unit tests, mocked CTFd API (no network)
ruff check server ctfd_mcp_server.py tests
```

The test suite mocks the CTFd API (`tests/conftest.py::FakeGateway`), so unit
tests run offline.

### Integration testing against a real CTFd

Run a local CTFd for live tests (recommended over the shared demo instance,
which serves HTML on public auth-gated routes):

```bash
git clone https://github.com/CTFd/CTFd.git /tmp/CTFd
docker compose -f /tmp/CTFd/docker-compose.yml up
# create a user/challenge, then:
CTFD_BASE_URL=http://localhost:8000 python ctfd_mcp_server.py
CTFD_BASE_URL=http://localhost:8000 uvicorn server.main:app --port 8001
curl http://localhost:8001/api/v1/health
```

---

## Security considerations

- **Credentials are memory-only.** By default nothing is written to
  `server_state.json`. Enabling `CTFD_PERSIST_SECRETS` is discouraged.
- **Secrets are never echoed.** Tool and API responses, error messages and logs
  redact tokens, cookies, passwords and flags (`server/utils.py`).
- **Every tool validates its input** before touching the network (`set_base_url`
  requires an absolute `http(s)` URL, `submit_flag` requires `confirm=True`,
  etc.).
- **Controlled retries.** Only idempotent `GET` requests are retried (once).
  Flag submissions are never automatically replayed.
- **Trust model.** The server is a local/dev tool: whoever can call its tools can
  point it at any CTFd instance and (with a valid credential) read data or submit
  flags. Do **not** expose the REST/SSE endpoints on an untrusted network.
- **File downloads** are written under `FILE_CACHE_DIR` with sanitized filenames
  (path-traversal protected).

---

## Limitations

- Requires CTFd **v3+**. The `/api/v1` routes used are standard CTFd v3 API
  routes.
- Form login depends on CTFd's web session flow (CSRF nonce extraction is
  best-effort). **API tokens are the recommended authentication method.**
- `difficulty` is not a standard CTFd field; challenge `value` (points) is
  returned instead.
- `solved` filtering uses CTFd's `solved_by_me` flag, which is only meaningful
  when authenticated.
- Instance "version" is reported only when it appears in the rendered page; CTFd
  has no public version API endpoint.
- **Tokens are per-instance.** CTFd redirects `/api/v1` calls to its login page
  when a credential is invalid. The server detects this and reports: *"the
  credential is not valid for THIS instance"* — a token from one CTFd instance
  never works on another.
- When `CTFD_USERNAME`/`CTFD_PASSWORD` are configured, the server **auto-logs-in
  on demand** (rotating the session cookie) whenever a call returns
  unauthenticated, so expired sessions self-heal.

---

## Contributing

Pull requests are welcome. Please:

1. Open an issue describing the change.
2. Add tests in `tests/` (mocked CTFd API preferred).
3. Run `python -m pytest -q` and `ruff check server ctfd_mcp_server.py tests`.
4. Do not ship credentials in code, tests, or commit `server_state.json` /
   `.env`.

## License

[MIT](LICENSE) — repository: <https://github.com/MrJamescot/ctfd-mcp-server>