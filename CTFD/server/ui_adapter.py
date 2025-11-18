from .state_manager import state

def ui_features():
    h = state.get_last_health()

    if not h:
        return {"download_enabled": False}

    return {
        "download_enabled": h["server_up"] and h["token_valid"]
    }
