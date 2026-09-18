# Demo

This walkthrough uses the public CTFd demo instance (`demo.ctfd.io`) with the
**REST** interface (simplest to follow). The MCP tools mirror these endpoints
one-to-one, so the same flow works through an MCP client.

> ⚠️ `demo.ctfd.io` serves HTML (not JSON) on public auth-gated API routes, so
> unauthenticated `challenges` calls will report a structured `CTFdAPIError`.
> Use a **local CTFd** (see README → _Integration testing_) or an authenticated
> token for full results — the client surfaces this honestly instead of faking a
> result.

---

## 1. Start the server

```bash
cp .env.example .env
# .env:  CTFD_BASE_URL=https://demo.ctfd.io
#        CTFD_ADMIN_TOKEN=ctfd_...   (optional, for authenticated flows)

uvicorn server.main:app --port 8000
```

```bash
> curl -s http://localhost:8000/api/v1/health
{
  "status": "ok",
  "ctfd_reachable": true,
  "api_ok": false,
  "authenticated": null,
  "auth_mode": "none",
  "message": "challenges probe failed (HTTP 200)"
}
```

`ctfd_reachable: true` confirms the instance answers. The probe that fetches
`/api/v1/challenges` fails here because the demo serves HTML for that route —
exactly the honest behaviour described above.

## 2. Environment / auth checks

```bash
> curl -s http://localhost:8000/api/v1/instance_info
{
  "base_url": "demo.ctfd.io",
  "reachable": true,
  "api_ok": true,
  "public_scoreboard": true,
  "auth_mode": "none",
  "configured": true,
  "detected_version": null,
  "notes": []
}

> curl -s http://localhost:8000/api/v1/auth_status
{
  "authenticated": null,
  "configured": false,
  "auth_mode": "none",
  "username": null,
  "note": "No token/cookie/credentials configured."
}
```

No secrets appear anywhere.

## 3. Set a token (memory only)

```bash
> curl -s -X POST http://localhost:8000/api/v1/set_token \
    -H "Content-Type: application/json" -d '{"token":"ctfd_YOUR_TOKEN"}'
{ "success": true, "auth_mode": "token" }

> curl -s -X POST http://localhost:8000/api/v1/auth_status
{ "authenticated": "yes", "configured": true, "auth_mode": "token", "username": null, "note": "..." }
```

## 4. Challenges (with a working/authenticated instance)

```bash
# paginated + filtered
curl "http://localhost:8000/api/v1/challenges?category=web&per_page=10&solved=false"

# one challenge by id or name
curl "http://localhost:8000/api/v1/challenges/cookies"

# shape of a list response:
{ "items": [ { "id": 3, "name": "cookie-monster", "category": "web",
               "value": 200, "solved_by_me": false, "solves": 12, "type": "standard" } ],
  "meta": { "page": 1, "per_page": 10, "total": 42, "has_more": true },
  "count": 1 }
```

## 5. Download a challenge file

```bash
> curl -s http://localhost:8000/api/v1/files/12/download
{ "success": true, "path": "/home/you/ctfd-mcp-server/file_cache/12.bin", "file_id": 12 }
```

Filenames are sanitized (`safe_filename`) — no path traversal.

## 6. Submit a flag (explicit confirm)

```bash
> curl -s -X POST http://localhost:8000/api/v1/submit \
    -H "Content-Type: application/json" \
    -d '{"challenge_id":3,"flag":"flag{wrong}","confirm":true}'
{ "success": false, "challenge_id": 3, "status": "incorrect",
  "message": "That flag is incorrect", "solved": false }

> curl -s -X POST http://localhost:8000/api/v1/submit \
    -H "Content-Type: application/json" \
    -d '{"challenge_id":3,"flag":"flag{right}","confirm":true}'
{ "success": true, "challenge_id": 3, "status": "correct",
  "message": "Correct!", "solved": true }
```

Omitting `confirm` (or setting it to `false`) returns a `ValidationError` — the
agent must explicitly intend to submit. Retries are never auto-replayed.

## 7. Leaderboard

```bash
> curl -s http://localhost:8000/api/v1/scoreboard
{ "success": true, "data": [ { "name": "hacker", "score": 1600, "solves": 12 } ] }
```

---

## MCP (same flow, agent-facing)

With `ctfd_mcp_server.py` registered as an MCP server, the identical steps use
the MCP tools:

```
set_base_url(url="https://demo.ctfd.io")       → {"success": true}
set_token(token="ctfd_YOUR_TOKEN")             → {"success": true, "auth_mode": "token"}
health()                                       → reachability/API/auth checks
challenges(category="web", solved=false)       → paginated items (id, name, value, ...)
challenge(identifier="cookies")                → full detail + files
submit_flag(flag="flag{...}", challenge_id=3, confirm=true) → correct/incorrect
scoreboard()                                   → standings
download_file(file_id=12)                      → saves under file_cache/
```

Tools return JSON text; errors are structured, e.g.
`{"error": {"type": "ChallengeNotFoundError", "message": "Challenge '99' not found (or not visible)."}}`.