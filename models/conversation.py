from datetime import datetime
from typing import Dict, List

class ConversationMessage:
    def __init__(self, content: str, role: str, timestamp: datetime = None):
        self.content = content
        self.role = role  # 'user' or 'assistant'
        self.timestamp = timestamp or datetime.utcnow()
    
    def to_dict(self) -> Dict:
        return {
            "content": self.content,
            "role": self.role,
            "timestamp": self.timestamp.isoformat()
        }

class Conversation:
    def __init__(self, user_id: str, title: str = "New Conversation"):
        self.id = None
        self.user_id = user_id
        self.title = title
        self.messages: List[ConversationMessage] = []
        self.context = {
            "user_preferences": {},
            "current_tasks": [],
            "past_conversations": [],
            "user_schedule": {}
        }
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def add_message(self, content: str, role: str):
        message = ConversationMessage(content, role)
        self.messages.append(message)
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "messages": [msg.to_dict() for msg in self.messages],
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }