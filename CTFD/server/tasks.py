from fastapi import BackgroundTasks
from .ctfd_client import CTFdClient
import asyncio

client = CTFdClient()

async def _sync_scoreboard_task(callback=None):
    try:
        data = await client.get_scoreboard()
        if callback:
            await callback(data)
        return data
    except Exception:
        return None

def schedule_sync_scoreboard(background_tasks: BackgroundTasks):
    background_tasks.add_task(asyncio.ensure_future, _sync_scoreboard_task())
    return {"status": "scheduled"}
