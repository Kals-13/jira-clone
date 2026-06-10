from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
import json
import logging
from collections import deque
import uuid
import datetime
from app.core.metrics import MetricsCollector

logger = logging.getLogger("jiralite.websocket")
router = APIRouter()

# Sliding replay cache capturing the last 500 mutation events across all boards
EVENT_HISTORY_LOG = deque(maxlen=500)

class ConnectionManager:
    def __init__(self):
        # Maps project_id -> list of tuples: (WebSocket, user_id)
        self.active_connections: dict[str, list[tuple[WebSocket, str]]] = {}

    async def connect(self, websocket: WebSocket, project_id: str, user_id: str):
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append((websocket, user_id))
        logger.info(f"Client {user_id} joined project channel: {project_id}")

        # Update metrics
        total_conns = sum(len(conns) for conns in self.active_connections.values())
        MetricsCollector.set_websocket_connections(total_conns)

        # Broadcast updated presence list immediately on connection
        await self.broadcast_presence(project_id)

    def disconnect(self, websocket: WebSocket, project_id: str, user_id: str):
        if project_id in self.active_connections:
            # Safely remove the user's specific connection entry
            self.active_connections[project_id] = [
                conn for conn in self.active_connections[project_id] if conn[0] != websocket
            ]
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
        logger.info(f"Client {user_id} disconnected from project channel: {project_id}")

        # Update metrics
        total_conns = sum(len(conns) for conns in self.active_connections.values())
        MetricsCollector.set_websocket_connections(total_conns)

    async def broadcast_to_project(self, project_id: str, message: dict, record_history: bool = True):
        """Broadcasts a payload and logs it to history for missed event recovery."""
        if record_history and "event_id" not in message:
            message["event_id"] = str(uuid.uuid4())
            message["timestamp"] = datetime.datetime.utcnow().isoformat()
            EVENT_HISTORY_LOG.append({"project_id": project_id, "data": message})

        if project_id in self.active_connections:
            payload = json.dumps(message)
            for connection, _ in self.active_connections[project_id]:
                try:
                    await connection.send_text(payload)
                except Exception as e:
                    logger.error(f"Failed to send WS broadcast frame: {e}")

    async def broadcast_presence(self, project_id: str):
        """Assembles a list of unique active user IDs on a board and broadcasts it."""
        if project_id not in self.active_connections:
            return
        active_users = list({user_id for _, user_id in self.active_connections[project_id]})
        presence_payload = {
            "event_type": "presence_update",
            "active_users": active_users,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
        # Send presence frame without recording it to the database mutation history
        await self.broadcast_to_project(project_id, presence_payload, record_history=False)

    async def replay_missed_events(self, websocket: WebSocket, project_id: str, last_seen_event_id: str):
        """Scans the event buffer log and plays back missing items sequentially."""
        found_anchor = False
        replay_queue = []

        for item in EVENT_HISTORY_LOG:
            if item["project_id"] == project_id:
                if found_anchor:
                    replay_queue.append(item["data"])
                elif item["data"].get("event_id") == last_seen_event_id:
                    found_anchor = True

        for event in replay_queue:
            try:
                await websocket.send_text(json.dumps(event))
            except Exception as e:
                logger.error(f"Failed to stream historical replay frame: {e}")
                break

manager = ConnectionManager()

@router.websocket("/board/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str, user_id: str = "anonymous"):
    await manager.connect(websocket, project_id, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            packet = json.loads(data)
            
            if packet.get("action") == "replay_request":
                last_seen_id = packet.get("last_seen_event_id")
                await manager.replay_missed_events(websocket, project_id, last_seen_id)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, project_id, user_id)
        # Ensure presence list drops user on departure
        await manager.broadcast_presence(project_id)