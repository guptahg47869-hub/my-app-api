from typing import Set
from fastapi import WebSocket

class WSManager:
    def __init__(self): 
        self.active: Set[WebSocket] = set()
    async def connect(self, ws: WebSocket):
        await ws.accept(); self.active.add(ws)
    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
    async def broadcast(self, message: dict):
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)

manager = WSManager()
