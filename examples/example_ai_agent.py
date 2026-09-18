"""
Example: AI agent calls the CTFd MCP server REST endpoints to orchestrate a solve flow.
This is a skeleton; replace `solve_challenge_logic` with your actual solver.
"""
import requests

# MATCH the MCP server's configured port (default 8000).
REST_BASE = "http://localhost:8000/api/v1"
TOKEN = "PUT_TOKEN_HERE"  # or call /set_token at runtime


def set_token(token):
    r = requests.post(f"{REST_BASE}/set_token", json={"token": token})
    r.raise_for_status()
    return r.json()


def list_challenges(**filters):
    r = requests.get(f"{REST_BASE}/challenges", params=filters)
    r.raise_for_status()
    return r.json()


def get_challenge(identifier):
    r = requests.get(f"{REST_BASE}/challenges/{identifier}")
    r.raise_for_status()
    return r.json()


def download_file(fid):
    r = requests.get(f"{REST_BASE}/files/{fid}/download")
    r.raise_for_status()
    return r.json()


def submit_flag(identifier, flag):
    r = requests.post(
        f"{REST_BASE}/submit",
        json={"challenge_id": identifier, "flag": flag, "confirm": True},
    )
    r.raise_for_status()
    return r.json()


def solve_challenge_logic(challenge):
    # PLACEHOLDER: implement your solver, e.g.:
    # - if the challenge lists files, download and analyze them
    # - parse the description / hints for patterns
    # Return the flag text, or None if you cannot solve it.
    return "flag{example_flag_from_logic}"


if __name__ == "__main__":
    set_token(TOKEN)
    page = list_challenges(page=1, per_page=25)
    for ch in page.get("items", []):  # summaries: id, name, category, value, ...
        cid = ch.get("id")
        print("Trying challenge", cid, ch.get("name"))
        detail = get_challenge(cid)
        flag = solve_challenge_logic(detail)
        if flag:
            resp = submit_flag(cid, flag)
            print("submit response:", resp)