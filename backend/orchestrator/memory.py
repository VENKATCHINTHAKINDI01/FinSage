"""
Conversation and Semantic Memory
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Track conversation history."""
    
    def __init__(self, user_id: str, max_turns: int = 20):
        self.user_id = user_id
        self.max_turns = max_turns
        self.turns: List[Dict[str, Any]] = []
    
    async def add_turn(
        self,
        query: str,
        agent_responses: Dict[str, Any],
        total_savings: float = 0
    ) -> None:
        """Add conversation turn."""
        turn = {
            "query": query,
            "responses": agent_responses,
            "savings": total_savings,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.turns.append(turn)
        
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]
        
        logger.info(f"Turn {len(self.turns)} added for user {self.user_id}")
    
    def get_context(self, num_turns: int = 3) -> str:
        """Get recent conversation context."""
        recent = self.turns[-num_turns:] if len(self.turns) >= num_turns else self.turns
        
        lines = []
        for turn in recent:
            lines.append(f"Q: {turn['query'][:80]}...")
            lines.append(f"Savings: ₹{turn['savings']:,.0f}")
        
        return "\n".join(lines) if lines else "No history"
    
    def has_history(self) -> bool:
        """Check if conversation history exists."""
        return len(self.turns) > 0


class SemanticMemory:
    """Learn facts about user."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.facts: Dict[str, List[Dict[str, Any]]] = {
            "income_sources": [],
            "deductions": [],
            "strategies": []
        }
    
    async def learn_income_source(self, source_type: str, amount: float):
        """Learn income source."""
        for existing in self.facts["income_sources"]:
            if existing["type"].lower() == source_type.lower():
                existing["count"] = existing.get("count", 1) + 1
                return
        
        self.facts["income_sources"].append({
            "type": source_type,
            "amount": amount,
            "count": 1
        })
        
        logger.info(f"Learned income source: {source_type}")
    
    async def learn_deduction(self, code: str, amount: float):
        """Learn deduction."""
        for existing in self.facts["deductions"]:
            if existing["code"].lower() == code.lower():
                existing["count"] = existing.get("count", 1) + 1
                return
        
        self.facts["deductions"].append({
            "code": code,
            "amount": amount,
            "count": 1
        })
        
        logger.info(f"Learned deduction: {code}")
    
    def get_known_deductions(self) -> List[str]:
        """Get previously known deductions."""
        return [d["code"] for d in self.facts["deductions"]]


# Global memory stores
user_memories: Dict[str, Dict[str, Any]] = {}


def get_or_create_memory(user_id: str) -> Dict[str, Any]:
    """Get or create memory for user."""
    if user_id not in user_memories:
        user_memories[user_id] = {
            "conversation": ConversationMemory(user_id),
            "semantic": SemanticMemory(user_id)
        }
    
    return user_memories[user_id]
