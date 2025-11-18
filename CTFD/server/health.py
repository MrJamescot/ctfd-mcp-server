from server.gateway import gateway
from .state_manager import state

async def perform_health_check():
    res = await gateway.request("GET", "/challenges")

    status = {
        "server_up": True,
        "token_valid": True,
        "cookie_valid": True,
        "raw": res,
    }

    if "error" in res:
        if res["error"] == "forbidden":
            status["token_valid"] = False
            status["cookie_valid"] = False
        status["server_up"] = False

    state.set_last_health(status)
    return status
