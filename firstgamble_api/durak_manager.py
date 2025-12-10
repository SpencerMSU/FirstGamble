import uuid
import asyncio
import time
import json
from typing import Dict, List
from fastapi import WebSocket, WebSocketDisconnect

from .durak_logic import DurakGame
from .redis_utils import add_points, get_balance, clamp_balance, get_redis, USERS_ZSET, key_balance

# Durak Constants
JOIN_COST = 30
WIN_REWARD = 100
READY_TIMEOUT = 30 # seconds

class DurakManager:
    def __init__(self):
        self.rooms: Dict[str, DurakGame] = {}
        self.connections: Dict[str, List[WebSocket]] = {} # room_id -> [ws]
        self.user_room_map: Dict[int, str] = {} # uid -> room_id
        self.timers: Dict[str, asyncio.Task] = {} # room_id -> task (for ready check)

    async def create_room(self, uid: int, name: str, settings: Dict) -> str:
        # Check balance
        bal = await get_balance(uid)
        if bal < JOIN_COST:
            return None

        # Deduct
        await add_points(uid, -JOIN_COST, "durak_create")

        room_id = str(uuid.uuid4())[:8]
        game = DurakGame(room_id, settings)
        game.add_player(uid, name)

        self.rooms[room_id] = game
        self.connections[room_id] = []
        self.user_room_map[uid] = room_id

        # Start ready timer check
        # self.timers[room_id] = asyncio.create_task(self.check_ready_timeout(room_id))

        return room_id

    async def join_room(self, uid: int, name: str, room_id: str) -> bool:
        game = self.rooms.get(room_id)
        if not game: return False

        if any(p.uid == uid for p in game.players):
            return True # Rejoin

        bal = await get_balance(uid)
        if bal < JOIN_COST: return False

        if game.add_player(uid, name):
            await add_points(uid, -JOIN_COST, "durak_join")
            self.user_room_map[uid] = room_id
            await self.broadcast_state(room_id)
            return True
        return False

    async def connect(self, websocket: WebSocket, room_id: str, uid: int):
        await websocket.accept()
        if room_id not in self.connections:
            self.connections[room_id] = []
        self.connections[room_id].append(websocket)

        # Send initial state
        game = self.rooms.get(room_id)
        if game:
            await websocket.send_json({"type": "state", "payload": game.get_snapshot(uid)})

            # Start Ready Timer if not running and game waiting
            if game.state == "waiting" and room_id not in self.timers:
                 self.timers[room_id] = asyncio.create_task(self.check_ready_timeout(room_id))

    def disconnect(self, websocket: WebSocket, room_id: str, uid: int):
        if room_id in self.connections:
            if websocket in self.connections[room_id]:
                self.connections[room_id].remove(websocket)
        # We don't remove player from game object on disconnect to allow reconnect

    async def handle_message(self, room_id: str, uid: int, data: Dict):
        game = self.rooms.get(room_id)
        if not game: return

        action = data.get("action")

        if action == "ready":
            game.set_ready(uid, True)
            # Check if all ready
            if all(p.is_ready for p in game.players) and len(game.players) >= 2:
                # Cancel timer
                if room_id in self.timers:
                    self.timers[room_id].cancel()
                    del self.timers[room_id]
                game.start_game()

        elif action == "attack":
            game.action_attack(uid, data.get("card"))

        elif action == "defend":
            game.action_defend(uid, data.get("target_idx"), data.get("card"))

        elif action == "take":
            game.action_take(uid)

        elif action == "pass":
            game.action_pass(uid)

        elif action == "transfer":
            game.action_transfer(uid, data.get("card"))

        # Check Win
        if game.state == "finished":
            await self.process_win(game)

        await self.broadcast_state(room_id)

    async def broadcast_state(self, room_id: str):
        game = self.rooms.get(room_id)
        if not game: return
        conns = self.connections.get(room_id, [])

        # We need to send personalized state to each connection?
        # Since connections don't map 1:1 to uid easily in simple list,
        # we can't easily filter hand.
        # Solution: Store (ws, uid) tuple in connections
        # Update connect/disconnect logic?
        pass # Fixed below

    async def check_ready_timeout(self, room_id: str):
        try:
            while True:
                await asyncio.sleep(5)
                game = self.rooms.get(room_id)
                if not game or game.state != "waiting": break

                now = time.time()
                changed = False
                to_remove = []

                for p in game.players:
                    if not p.is_ready and (now - p.last_active > READY_TIMEOUT):
                         # Kick
                         to_remove.append(p.uid)

                for uid in to_remove:
                    game.remove_player(uid)
                    changed = True
                    # Optional: Refund? Rules didn't specify. Assuming forfeit fee.

                if not game.players:
                    # Close room
                    del self.rooms[room_id]
                    break

                if changed:
                    await self.broadcast_state(room_id)

        except asyncio.CancelledError:
            pass

    async def process_win(self, game: DurakGame):
        # Distribute prizes
        # 1st place gets 100? Or only the absolute winner?
        # "victory in the game gives 100 points"
        # Assuming only 1 winner (the first one out, or last remaining is loser?)
        # Durak: 1 loser. Others are winners? Or 1st place?
        # Usually Durak has 1 loser. But "Victory gives 100" implies positive reward.
        # Let's give 100 to everyone who is NOT the durak (loser).

        loser_uid = None
        # In DurakGame logic we mark is_out. The last one remaining is not out.
        # Wait, my logic marks is_out when hand empty.
        # So the one NOT is_out at end is the loser.

        active = [p for p in game.players if not p.is_out]
        if len(active) == 1:
            loser_uid = active[0].uid

        for p in game.players:
            if p.uid != loser_uid:
                await add_points(p.uid, WIN_REWARD, "durak_win")

        # Room cleanup handled by inactivity or manual leave later?
        # For now keep it open to show results.

    # Revised Connection Handling for Per-User State
    async def connect_auth(self, websocket: WebSocket, room_id: str, uid: int):
        await websocket.accept()
        if room_id not in self.connections:
            self.connections[room_id] = []
        self.connections[room_id].append((websocket, uid))

        game = self.rooms.get(room_id)
        if game:
             await websocket.send_json({"type": "state", "payload": game.get_snapshot(uid)})
             if game.state == "waiting" and room_id not in self.timers:
                 self.timers[room_id] = asyncio.create_task(self.check_ready_timeout(room_id))

    async def broadcast_state(self, room_id: str):
        game = self.rooms.get(room_id)
        if not game: return

        tuples = self.connections.get(room_id, [])
        dead_ws = []

        for ws, uid in tuples:
            try:
                snapshot = game.get_snapshot(uid)
                await ws.send_json({"type": "state", "payload": snapshot})
            except:
                dead_ws.append((ws, uid))

        for item in dead_ws:
            if item in tuples:
                tuples.remove(item)

durak_manager = DurakManager()
