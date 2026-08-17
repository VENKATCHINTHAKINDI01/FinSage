"""
WebSocket endpoint - /ws/agent-stream/{session_id}
Stream agent activity in real-time to frontend.
Clients see live agent thinking and results.
"""

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])

# Connection manager for WebSocket clients
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, conversation_id: str, websocket: WebSocket):
        """Register a new WebSocket connection."""
        await websocket.accept()
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = set()
        self.active_connections[conversation_id].add(websocket)
        logger.info(f"Client connected to {conversation_id}")

    def disconnect(self, conversation_id: str, websocket: WebSocket):
        """Unregister a WebSocket connection."""
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].discard(websocket)
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]
        logger.info(f"Client disconnected from {conversation_id}")

    async def broadcast(self, conversation_id: str, message: dict):
        """Send message to all clients in a conversation."""
        if conversation_id not in self.active_connections:
            return

        # Send to all connected clients
        disconnected = set()
        for websocket in self.active_connections[conversation_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                disconnected.add(websocket)

        # Remove disconnected clients
        for websocket in disconnected:
            self.disconnect(conversation_id, websocket)


# Global connection manager
manager = ConnectionManager()


async def _authenticate(websocket: WebSocket, token: str | None) -> str | None:
    """Resolve the user from a JWT, or close the socket.

    AGT-007 security fix. The previous signature was:

        user_id: str = Query(...)

    — the caller simply *told us* who they were. Anyone who could guess or
    observe a conversation id could open
    `/ws/agent-stream/{id}?user_id=<someone else>` and stream another person's
    agent activity, including their financial figures. There was no check of
    any kind.

    HTTP handlers cannot set headers on a browser WebSocket, so the token
    arrives as a query parameter or via the subprotocol. It is a real signed
    JWT either way, and it is verified.
    """
    from backend.security.jwt_handler import verify_token

    if not token:
        await websocket.close(code=4401, reason="authentication required")
        return None

    payload = verify_token(token, token_type="access")
    if not payload:
        await websocket.close(code=4401, reason="invalid or expired token")
        return None

    user_id = payload.get("sub") or payload.get("user_id")
    if not user_id:
        await websocket.close(code=4401, reason="token carries no subject")
        return None
    return str(user_id)


@router.websocket("/agent-stream/{conversation_id}")
async def websocket_agent_stream(
    websocket: WebSocket,
    conversation_id: str,
    token: str | None = Query(default=None),
):
    """
    WebSocket endpoint for live agent streaming.

    Features:
    - Real-time agent activity updates
    - Live thinking/reasoning from agents
    - Streaming results as they complete
    - Error notifications

    Connection:
    ```javascript
    const ws = new WebSocket(
      `ws://localhost:8000/ws/agent-stream/${conversationId}?user_id=${userId}`
    );

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      console.log(message.type, message.data);
    };
    ```

    Message Types:
    - "connection_established" - Connection opened
    - "agent_start" - Agent started executing
    - "agent_thinking" - Agent reasoning (streaming)
    - "agent_complete" - Agent finished with result
    - "aggregation_start" - Result aggregation started
    - "final_response" - Final response ready
    - "error" - Error occurred
    - "connection_closed" - Connection closed
    """

    user_id = await _authenticate(websocket, token)
    if user_id is None:
        return

    await manager.connect(conversation_id, websocket)

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connection_established",
            "conversation_id": conversation_id,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        logger.info(f"WebSocket connected: conversation={conversation_id}, user={user_id}")

        # Keep connection alive and listen for messages
        while True:
            data = await websocket.receive_json()

            # Handle incoming messages (e.g., new queries)
            if data.get("type") == "query":
                query_text = data.get("query", "")

                logger.info(f"Received query on WebSocket: {query_text[:50]}")

                await run_agent_execution(conversation_id, query_text, user_id)

            elif data.get("type") == "ping":
                # Respond to ping
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

    except WebSocketDisconnect:
        manager.disconnect(conversation_id, websocket)
        logger.info(f"WebSocket disconnected: {conversation_id}")

        # Broadcast disconnection to other clients
        await manager.broadcast(conversation_id, {
            "type": "connection_closed",
            "conversation_id": conversation_id
        })

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(conversation_id, websocket)

        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except Exception:
            logger.debug('failed to notify a closing client', exc_info=True)


async def run_agent_execution(conversation_id: str, query: str, user_id: str) -> None:
    """Run the real orchestrator and stream its actual results.

    AGT-007. This used to be `simulate_agent_execution`: a fixed script that
    broadcast invented figures — a hardcoded "₹1,600 in savings" no computation
    ever produced. That is precisely what `docs/IMPLEMENTATION_PLAN.md` §1
    forbids ("no rupee figure shown to a user may originate from a language
    model" applies just as much to one that never even ran). This calls the
    same orchestration path `/api/v1/chat/query` uses and broadcasts only what
    it actually returns.

    A failure here becomes a broadcast `error` event, not a dropped
    connection — the socket stays open for the next query.
    """
    from backend.db.postgres import get_session_maker
    from backend.orchestrator.graph import db_session_var, get_orchestrator

    started = time.perf_counter()
    try:
        orch = get_orchestrator()
        if orch is None:
            raise RuntimeError("orchestrator not initialized")

        session_maker = await get_session_maker()
        async with session_maker() as session:
            token = db_session_var.set(session)
            try:
                from backend.api.chat import get_user_context, intent_detector

                context_data = await get_user_context(user_id, session)
                intent_result = await intent_detector.detect_intent(query)
                intent = intent_result.intent.value if hasattr(intent_result, "intent") else "general"
                agents_to_invoke = getattr(intent_result, "agents_to_invoke", None)

                user_context = {
                    "user_id": user_id,
                    "annual_income": context_data.get("annual_income", 0.0),
                    "employment_type": context_data.get("employment_type", "individual"),
                    **context_data,
                }

                result = await orch.orchestrate(
                    user_query=query,
                    user_id=user_id,
                    user_context=user_context,
                    intent=intent,
                    agents_to_invoke=agents_to_invoke,
                    conversation_id=conversation_id,
                )
            finally:
                db_session_var.reset(token)

        agent_results = result.get("agent_results", {})
        for agent_name, agent_result in agent_results.items():
            await manager.broadcast(conversation_id, {
                "type": "agent_start",
                "agent": agent_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            if hasattr(agent_result, "result"):
                res_dict = agent_result.result
            elif isinstance(agent_result, dict):
                res_dict = agent_result.get("result", {})
            else:
                res_dict = {}

            await manager.broadcast(conversation_id, {
                "type": "agent_complete",
                "agent": agent_name,
                "result": res_dict,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        await manager.broadcast(conversation_id, {
            "type": "final_response",
            "response": result.get("response", ""),
            "agent_responses": {
                name: (r.result if hasattr(r, "result") else r.get("result", {}) if isinstance(r, dict) else {})
                for name, r in agent_results.items()
            },
            "total_execution_time_ms": round((time.perf_counter() - started) * 1000, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as exc:
        logger.exception("Agent execution failed for conversation %s", conversation_id)
        await manager.broadcast(conversation_id, {
            "type": "error",
            "message": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


@router.get("/connections-count")
async def get_connections_count():
    """Get count of active WebSocket connections (for monitoring)."""
    total = sum(len(clients) for clients in manager.active_connections.values())
    return {
        "active_conversations": len(manager.active_connections),
        "total_clients": total
    }
