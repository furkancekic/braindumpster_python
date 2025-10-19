from datetime import datetime
from typing import Dict, List, Optional

class User:
    def __init__(self, uid: str, email: str, display_name: str = None):
        self.uid = uid
        self.email = email
        self.display_name = display_name
        self.created_at = datetime.utcnow()
        self.preferences = {
            "timezone": "UTC",
            "notification_preferences": {
                "email": True,
                "push": True,
                "reminder_advance": 15  # minutes
            }
        }
    
    def to_dict(self) -> Dict:
        return {
            "uid": self.uid,
            "email": self.email,
            "display_name": self.display_name,
            "created_at": self.created_at.isoformat(),
            "preferences": self.preferences
        }
    
    @classmethod
    def from_dict(cls, data: Dict):
        user = cls(data["uid"], data["email"], data.get("display_name"))
        user.created_at = datetime.fromisoformat(data["created_at"])
        user.preferences = data.get("preferences", user.preferences)
        return user