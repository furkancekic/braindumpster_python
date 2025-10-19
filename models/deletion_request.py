from datetime import datetime
from typing import Dict, Optional

class DeletionRequest:
    def __init__(
        self,
        request_id: str,
        user_id: str,
        user_email: str,
        confirmation_code: str,
        reason: str = "",
        status: str = "pending",
        job_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None
    ):
        self.request_id = request_id
        self.user_id = user_id
        self.user_email = user_email
        self.confirmation_code = confirmation_code
        self.reason = reason
        self.status = status  # pending, confirmed, processing, completed, failed, cancelled
        self.job_id = job_id
        self.expires_at = expires_at
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.completed_at = completed_at
        self.error_message = error_message

    def to_dict(self) -> Dict:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "confirmation_code": self.confirmation_code,
            "reason": self.reason,
            "status": self.status,
            "job_id": self.job_id,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            request_id=data["request_id"],
            user_id=data["user_id"],
            user_email=data["user_email"],
            confirmation_code=data["confirmation_code"],
            reason=data.get("reason", ""),
            status=data.get("status", "pending"),
            job_id=data.get("job_id"),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            error_message=data.get("error_message")
        )