import re
import html
import json
import asyncio
import logging
import time
from uuid import uuid4
from typing import List, Set
from fastapi import WebSocket

from redis.asyncio import Redis

from .config import REDIS_HOST, REDIS_PORT, REDIS_DB
from .redis_utils import get_redis

logger = logging.getLogger(__name__)

class ChatManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.ban_patterns = [
            re.compile(r"fascis[mt]", re.IGNORECASE),
            re.compile(r"nazi", re.IGNORECASE),
            re.compile(r"hitler", re.IGNORECASE),
            re.compile(r"swastika", re.IGNORECASE),
            re.compile(r"zig\s*heil", re.IGNORECASE),
            re.compile(r"white\s*power", re.IGNORECASE),
            re.compile(r"terroris[mt]", re.IGNORECASE),
            re.compile(r"isis", re.IGNORECASE),
        ]
        self.pubsub_task = None
        self.channel_name = "chat:global"
        self.history_key = "chat:history:zset"
        self.pinned_key = "chat:pinned"

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    def filter_message(self, text: str) -> str:
        clean_text = html.escape(text)
        for pattern in self.ban_patterns:
            if pattern.search(clean_text):
                return None
        return clean_text

    async def broadcast(self, message: str, sender: str, timestamp: int = None):
        """
        Publishes the message to Redis.
        The listener task will pick it up and call broadcast_local.
        """
        ts = timestamp or int(time.time())
        payload = {
            "type": "message",
            "id": str(uuid4()),
            "timestamp": ts,
            "sender": sender,
            "text": message
        }
        json_payload = json.dumps(payload)
        try:
            r = await get_redis()
            # Store history using ZSET with timestamp as score
            await r.zadd(self.history_key, {json_payload: ts})

            # Remove messages older than 3 days
            cutoff = int(time.time()) - (3 * 86400)
            await r.zremrangebyscore(self.history_key, "-inf", cutoff)

            # Only publish if there are active listeners (optimization) or just publish always
            # but we catch errors if redis publish fails for some reason
            await r.publish(self.channel_name, json_payload)
        except Exception as e:
            logger.exception(f"Error publishing chat message: {e}")
            # Re-raise so the API knows it failed?
            # Or suppress? If we suppress, user pays points but msg not sent.
            # Ideally we should refund or fail earlier.
            # Given the user sees 500, it's raising.
            raise e

    async def get_history(self) -> List[dict]:
        """Returns the recent chat history."""
        try:
            r = await get_redis()
            # Get all messages from ZSET (ordered by score/timestamp)
            raw = await r.zrange(self.history_key, 0, -1)
            return [json.loads(x) for x in raw]
        except Exception as e:
            logger.error(f"Error getting chat history: {e}")
            return []

    async def get_pinned(self) -> str:
        """Returns the current pinned message text or empty string."""
        try:
            r = await get_redis()
            return (await r.get(self.pinned_key)) or ""
        except Exception:
            return ""

    async def set_pinned(self, text: str):
        """Sets the pinned message."""
        r = await get_redis()
        if not text:
            await r.delete(self.pinned_key)
        else:
            await r.set(self.pinned_key, text)

    async def broadcast_local(self, payload: dict):
        """
        Sends the message to all locally connected websockets.
        """
        to_remove = []
        for connection in self.active_connections:
            try:
                await connection.send_json(payload)
            except Exception:
                to_remove.append(connection)

        for conn in to_remove:
            self.disconnect(conn)

    async def start_redis_listener(self):
        """
        Starts a background task that listens to Redis channel and broadcasts locally.
        """
        if self.pubsub_task:
            return

        self.pubsub_task = asyncio.create_task(self._redis_listener())
        logger.info("Chat Redis listener started.")

    async def stop_redis_listener(self):
        """
        Stops the background listener task.
        """
        if self.pubsub_task:
            self.pubsub_task.cancel()
            try:
                await self.pubsub_task
            except asyncio.CancelledError:
                pass
            self.pubsub_task = None
            logger.info("Chat Redis listener stopped.")

    async def _redis_listener(self):
        # Create a dedicated connection for PubSub
        r = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(self.channel_name)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    try:
                        payload = json.loads(data)
                        await self.broadcast_local(payload)
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON in chat channel: {data}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in chat Redis listener: {e}")
        finally:
            await pubsub.unsubscribe(self.channel_name)
            await r.close()

chat_manager = ChatManager()
