"""
Example: AI agent calls MCP server endpoints to orchestrate solve flow.
This is a skeleton; replace `solve_challenge_logic` with actual solver.
"""
import requests

MCP_BASE = "http://localhost:9999/api/v1"
TOKEN = "PUT_TOKEN_HERE"  # or call /set_token

def set_token(token):
    r = requests.post(f"{MCP_BASE}/set_token", json={"token": token})
    return r.json()

def list_challenges():
    return requests.get(f"{MCP_BASE}/challenges").json()

def get_challenge(cid):
    return requests.get(f"{MCP_BASE}/challenges/{cid}").json()

def download_file(fid):
    return requests.get(f"{MCP_BASE}/files/{fid}").json()

def submit_flag(cid, flag):
    return requests.post(f"{MCP_BASE}/submit", json={"challenge_id": cid, "flag": flag}).json()

def solve_challenge_logic(challenge):
    # PLACEHOLDER: implement solver:
    # - if challenge has files: download and analyze
    # - if description contains hints: parse for patterns
    # Must be implemented by user (avoid sharing exploit code).
    return "flag{example_flag_from_logic}"

if __name__ == "__main__":
    # Example flow:
    # set_token(TOKEN)
    chs = list_challenges()
    for ch in chs.get("data", chs):  # some responses nested in 'data'
        cid = ch.get("id") or ch.get("challenge_id") or ch.get("id")
        print("Trying challenge", cid)
        detail = get_challenge(cid)
        # call your solver
        flag = solve_challenge_logic(detail)
        if flag:
            resp = submit_flag(cid, flag)
            print("submit response:", resp)
