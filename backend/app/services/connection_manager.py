import asyncio
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._connections: dict[int, list[WebSocket]] = {}

    def register(self, user_id: int, ws: WebSocket):
        self._connections.setdefault(user_id, []).append(ws)

    def unregister(self, user_id: int, ws: WebSocket):
        if user_id in self._connections:
            try:
                self._connections[user_id].remove(ws)
            except ValueError:
                pass

    async def push_to_user(self, user_id: int, payload: dict):
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                self.unregister(user_id, ws)

    async def broadcast(self, payload: dict):
        for uid in list(self._connections):
            await self.push_to_user(uid, payload)

    @property
    def connected_count(self) -> int:
        return sum(len(v) for v in self._connections.values())


manager = ConnectionManager()
