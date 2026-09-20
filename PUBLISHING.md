# Publishing & Distribution Guide

This project can be distributed through several popular platforms. This guide
explains how to get an account, wire up the repo, and trigger a release.
Most steps are **one-time setup**; after that, publishing is automatic whenever
you push a `v*` tag.

| Platform | What you get | Automation |
| -------- | ------------ | ---------- |
| [PyPI](https://pypi.org) | `pip install ctfd-mcp-server`, `uvx ctfd-mcp-server` | GitHub Action on `v*` tag |
| [Docker Hub](https://hub.docker.com) | `docker run mrjamescot/ctfd-mcp-server` | GitHub Action on `v*` tag |
| [Smithery](https://smithery.ai) | One-click install in Claude/Cursor/etc. | Manual submit once (`smithery.yaml` ready) |
| [MCP.so](https://mcp.so) | Directory listing | Manual submit once |
| [Model Context Protocol registry](https://registry.modelcontextprotocol.io) | Official registry entry | Manual submit via PR once |

> **One-time prerequisites** — you need accounts on PyPI, Docker Hub, Smithery,
> and MCP.so. The GitHub repo is already in place:
> `https://github.com/MrJamescot/ctfd-mcp-server`

---

## 0. Base URL (everything references this)

Repository: `https://github.com/MrJamescot/ctfd-mcp-server`
Docker image name: `mrjamescot/ctfd-mcp-server`
PyPI project name: `ctfd-mcp-server`

---

## 1. PyPI

1. Create an account at <https://pypi.org/account/register/> (and also
   <https://test.pypi.org> if you want to test first).
2. Verify your email, then go to
   **Account settings → API tokens → Add API token**.
   - Scope: project `ctfd-mcp-server` (or *whole account*).
   - Copy the token (it starts with `pypi-`).
3. On GitHub:
   - Repo → **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `PYPI_API_TOKEN`, value: the token.
4. Publish: push a tag → the `Publish to PyPI` workflow builds, checks, uploads,
   and creates a GitHub Release automatically.

```bash
git tag v1.0.0 && git push origin v1.0.0
```

### Alternative: Trusted Publishing (no token)

1. First publish once with the token above (this creates the PyPI project).
2. Then on PyPI: **Manage → Publishing → Add a new pending publisher**:
   - Owner: `MrJamescot`, Repository: `ctfd-mcp-server`, Workflow: `publish-pypi.yml`.
3. You can then remove `password:` from the workflow and keep the secret empty.

---

## 2. Docker Hub

1. Create an account at <https://hub.docker.com/signup>.
2. **Account Settings → Personal Access Tokens → Generate** (read/write access).
3. On GitHub add two repository secrets:
   - `DOCKER_USERNAME` = your Docker Hub username (`mrjamescot`).
   - `DOCKER_TOKEN` = the access token.
4. Publish: push a `v*` tag → the `Publish Docker Image` workflow builds and
   pushes `mrjamescot/ctfd-mcp-server:latest` and the version-tagged image.
5. First image must be created manually once: create repo
   `ctfd-mcp-server` on Docker Hub (public) so the workflow can push.

---

## 3. Smithery (mcp registry, one-click deploys)

1. Sign in at <https://smithery.ai> with your GitHub account.
2. Go to **Deploy a New MCP Server → Connect GitHub Repo** and select
   `MrJamescot/ctfd-mcp-server`.
3. Smithery reads `smithery.yaml` from this repo to build a deployable
   container (it configures the `ctfdBaseUrl` at deployment time).
4. Follow the onboarding; then the server appears on
   <https://smithery.ai/server/@MrJamescot/ctfd-mcp-server>.
5. The generated install snippet (for Claude Desktop / Cursor) can be added to
   the README afterwards.

---

## 4. MCP.so

1. Create an account (GitHub OAuth) at <https://mcp.so>.
2. **Submit Server → Paste the GitHub repo URL**
   (`https://github.com/MrJamescot/ctfd-mcp-server`).
3. Fill in tags/keywords: `ctf`, `ctfd`, `mcp`, `security`, `ai agent`.
4. It will pull the README automatically for the listing.

---

## 5. Official Model Context Protocol registry

The official registry is published via the
[`registry`](https://github.com/modelcontextprotocol/registry) project.

1. Fork `modelcontextprotocol/registry`.
2. Add your server to `servers/` (follow the existing JSON schema in the repo).
3. Open a Pull Request with the entry. Once merged, the server is listed on
   <https://registry.modelcontextprotocol.io>.

> Registries you should also consider: **[Glama](https://glama.ai/mcp/servers)**
> (AI marketplace) and **[Pulse](https://www.pulsemcp.com)**. Both accept GitHub
> submissions and boost discoverability.

---

## Versioning & releasing

This project follows **calendar-agnostic semver** in `pyproject.toml`
(`ctfd-mcp-server` version `1.0.0`). To cut a release:

```bash
# bump version in pyproject.toml, commit, then:
git tag v1.0.1
git push origin main
git push origin v1.0.1
```

Both GitHub Actions fire on the tag: the PyPI upload *and* the Docker image
push. The `Publish to PyPI` job also attaches the built wheels (`.whl` /
`.tar.gz`) to the GitHub Release.