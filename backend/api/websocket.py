"""
WebSocket endpoint - /ws/agent-stream/{session_id}
Stream agent activity in real-time to frontend.
Clients see live agent thinking and results.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Query
import logging
import json
import uuid
from typing import Set
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])

# Connection manager for WebSocket clients
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, Set[WebSocket]] = {}
    
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


@router.websocket("/agent-stream/{conversation_id}")
async def websocket_agent_stream(
    websocket: WebSocket,
    conversation_id: str,
    user_id: str = Query(...)
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
    
    await manager.connect(conversation_id, websocket)
    
    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connection_established",
            "conversation_id": conversation_id,
            "user_id": user_id,
            "timestamp": str(__import__('datetime').datetime.utcnow())
        })
        
        logger.info(f"WebSocket connected: conversation={conversation_id}, user={user_id}")
        
        # Keep connection alive and listen for messages
        while True:
            data = await websocket.receive_json()
            
            # Handle incoming messages (e.g., new queries)
            if data.get("type") == "query":
                query_text = data.get("query", "")
                
                logger.info(f"Received query on WebSocket: {query_text[:50]}")
                
                # Simulate agent execution with streaming
                await simulate_agent_execution(conversation_id, query_text)
            
            elif data.get("type") == "ping":
                # Respond to ping
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": str(__import__('datetime').datetime.utcnow())
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
        except:
            pass


async def simulate_agent_execution(conversation_id: str, query: str):
    """
    Simulate multi-agent execution with live streaming.
    In production, this would call the actual orchestrator.
    """
    
    import time
    
    # Agent 1: Tax Agent
    await manager.broadcast(conversation_id, {
        "type": "agent_start",
        "agent": "tax_deduction_agent",
        "timestamp": str(__import__('datetime').datetime.utcnow())
    })
    
    # Simulate thinking
    for i in range(3):
        await asyncio.sleep(0.5)
        await manager.broadcast(conversation_id, {
            "type": "agent_thinking",
            "agent": "tax_deduction_agent",
            "reasoning": f"Analyzing deductions... step {i+1}/3",
            "timestamp": str(__import__('datetime').datetime.utcnow())
        })
    
    # Send result
    await manager.broadcast(conversation_id, {
        "type": "agent_complete",
        "agent": "tax_deduction_agent",
        "result": {
            "deductions": [
                {"category": "Home Office", "amount": 5000},
                {"category": "Equipment", "amount": 3000}
            ],
            "total": 8000,
            "estimated_savings": 1600
        },
        "execution_time_ms": 1500,
        "timestamp": str(__import__('datetime').datetime.utcnow())
    })
    
    # Agent 2: Investment Agent
    await asyncio.sleep(0.5)
    
    await manager.broadcast(conversation_id, {
        "type": "agent_start",
        "agent": "investment_optimizer_agent",
        "timestamp": str(__import__('datetime').datetime.utcnow())
    })
    
    await asyncio.sleep(1.5)
    
    await manager.broadcast(conversation_id, {
        "type": "agent_complete",
        "agent": "investment_optimizer_agent",
        "result": {
            "recommendations": [
                {"type": "diversify", "action": "Move 20% to index funds"},
                {"type": "rebalance", "action": "Increase bonds to 40%"}
            ]
        },
        "execution_time_ms": 1000,
        "timestamp": str(__import__('datetime').datetime.utcnow())
    })
    
    # Aggregation
    await asyncio.sleep(0.3)
    
    await manager.broadcast(conversation_id, {
        "type": "aggregation_start",
        "timestamp": str(__import__('datetime').datetime.utcnow())
    })
    
    await asyncio.sleep(0.5)
    
    # Final response
    await manager.broadcast(conversation_id, {
        "type": "final_response",
        "response": "Based on analysis: Your estimated tax savings are ₹1,600. Consider diversifying your investments as recommended.",
        "total_execution_time_ms": 3000,
        "timestamp": str(__import__('datetime').datetime.utcnow())
    })


@router.get("/connections-count")
async def get_connections_count():
    """Get count of active WebSocket connections (for monitoring)."""
    total = sum(len(clients) for clients in manager.active_connections.values())
    return {
        "active_conversations": len(manager.active_connections),
        "total_clients": total
    }