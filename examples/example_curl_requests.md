# Example `curl` requests

Run the REST interface first (default port `8000`):

```bash
uvicorn server.main:app --port 8000
```

Set an API token (memory only — never stored to disk):

```bash
curl -X POST "http://localhost:8000/api/v1/set_token" \
  -H "Content-Type: application/json" \
  -d '{"token":"ctfd_YOUR_TOKEN_HERE"}'
```

List challenges — supports `page`, `per_page`, `category`, `search`, and
`solved` (true/false) filters:

```bash
curl "http://localhost:8000/api/v1/challenges?per_page=10&solved=false"
```

Get one challenge by id or name:

```bash
curl "http://localhost:8000/api/v1/challenges/5"
```

Download a challenge file to the server-side cache
(`/files/{id}/download`, returns the local cache path):

```bash
curl "http://localhost:8000/api/v1/files/12/download"
```

Submit a flag (requires `"confirm": true` — this is deliberately explicit so
an AI agent never submits accidentally):

```bash
curl -X POST "http://localhost:8000/api/v1/submit" \
  -H "Content-Type: application/json" \
  -d '{"challenge_id":5,"flag":"flag{test}","confirm":true}'
```

Health and auth checks:

```bash
curl "http://localhost:8000/api/v1/health"
curl "http://localhost:8000/api/v1/auth_status"
curl "http://localhost:8000/api/v1/instance_info"
```

Full endpoint table: see `README.md` under _Running the REST API (optional)_.