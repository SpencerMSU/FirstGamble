import re
import html
from typing import List, Set
from fastapi import WebSocket

class ChatManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # Basic list of banwords (regex patterns for flexibility)
        # Includes common variations, simple example set.
        self.ban_patterns = [
            re.compile(r"fascis[mt]", re.IGNORECASE),
            re.compile(r"nazi", re.IGNORECASE),
            re.compile(r"hitler", re.IGNORECASE),
            re.compile(r"swastika", re.IGNORECASE),
            re.compile(r"zig\s*heil", re.IGNORECASE),
            re.compile(r"white\s*power", re.IGNORECASE),
            # Add more specific RU/EN terms as needed for "forbidden in the world"
            re.compile(r"terroris[mt]", re.IGNORECASE),
            re.compile(r"isis", re.IGNORECASE),
        ]

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    def filter_message(self, text: str) -> str:
        """
        Returns the text if allowed, or None/Empty if banned.
        User asked to block: 'fascism/nazism etc'.
        Allowed: 'negr', 'mat'.
        """
        # 1. Clean HTML
        clean_text = html.escape(text)

        # 2. Check ban patterns
        for pattern in self.ban_patterns:
            if pattern.search(clean_text):
                return None # Blocked

        return clean_text

    async def broadcast(self, message: str, sender: str):
        # We broadcast a JSON structure
        payload = {"type": "message", "sender": sender, "text": message}
        to_remove = []
        for connection in self.active_connections:
            try:
                await connection.send_json(payload)
            except Exception:
                to_remove.append(connection)

        for conn in to_remove:
            self.disconnect(conn)

chat_manager = ChatManager()
