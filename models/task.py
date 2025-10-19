from datetime import datetime, timezone
from typing import Dict, List, Optional
from enum import Enum
import pytz

class TaskStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DELETED = "deleted"

class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class ReminderRecurrence(Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

class ReminderPriority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

class Task:
    def __init__(self, title: str, description: str, user_id: str,
                 due_date: datetime = None, priority: TaskPriority = TaskPriority.MEDIUM,
                 is_recurring: bool = False, recurring_pattern: Dict = None):
        self.id = None  # Will be set by Firebase
        self.title = title
        self.description = description
        self.user_id = user_id
        self.due_date = due_date
        self.priority = priority
        self.status = TaskStatus.PENDING
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.ai_generated = True
        self.conversation_id = None
        self.reminders = []
        self.subtasks = []
        self.is_recurring = is_recurring
        self.recurring_pattern = recurring_pattern or {}
        self.suggestions = []  # AI-generated suggestions for this task
        
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "user_id": self.user_id,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "ai_generated": self.ai_generated,
            "conversation_id": self.conversation_id,
            "reminders": [r.to_dict() for r in self.reminders],
            "subtasks": [s if isinstance(s, dict) else s.to_dict() for s in self.subtasks],
            "is_recurring": self.is_recurring,
            "recurring_pattern": self.recurring_pattern,
            "suggestions": self.suggestions
        }
    
    @classmethod
    def from_dict(cls, data: Dict):
        # Parse due_date with timezone handling
        due_date = None
        if data.get("due_date"):
            due_date = cls._parse_datetime_with_timezone(data["due_date"])
        
        task = cls(
            data["title"],
            data["description"],
            data["user_id"],
            due_date,
            TaskPriority(data["priority"]),
            data.get("is_recurring", False),
            data.get("recurring_pattern", {})
        )
        task.id = data.get("id")
        task.status = TaskStatus(data["status"])
        task.created_at = cls._parse_datetime_with_timezone(data["created_at"])
        task.updated_at = cls._parse_datetime_with_timezone(data["updated_at"])
        task.ai_generated = data.get("ai_generated", True)
        task.conversation_id = data.get("conversation_id")
        
        # Load reminders from dictionary
        task.reminders = []
        reminders_data = data.get("reminders", [])
        for reminder_data in reminders_data:
            # Parse reminder time with proper timezone handling
            reminder_time_str = reminder_data["reminder_time"]
            reminder_time = cls._parse_datetime_with_timezone(reminder_time_str)
            
            reminder = Reminder(
                task_id=reminder_data.get("task_id"),
                reminder_time=reminder_time,
                message=reminder_data["message"],
                notification=reminder_data.get("notification", {}),
                recurrence=reminder_data.get("recurrence", "none"),
                priority=reminder_data.get("priority", "normal")
            )
            reminder.id = reminder_data.get("id")
            reminder.sent = reminder_data.get("sent", False)
            
            # Parse created_at with timezone handling
            created_at_str = reminder_data.get("created_at", datetime.now(timezone.utc).isoformat())
            reminder.created_at = cls._parse_datetime_with_timezone(created_at_str)
            
            task.reminders.append(reminder)
        
        # Load subtasks
        task.subtasks = data.get("subtasks", [])

        # Load suggestions (AI-generated suggestions)
        task.suggestions = data.get("suggestions", [])

        return task
    
    @classmethod
    def _parse_datetime_with_timezone(cls, datetime_str) -> datetime:
        """Parse datetime string or object with proper timezone handling"""
        try:
            # Handle if it's already a datetime object (e.g., DatetimeWithNanoseconds from Firestore)
            if isinstance(datetime_str, datetime):
                dt = datetime_str
                # Ensure it has timezone info
                if dt.tzinfo is None:
                    turkey_tz = pytz.timezone('Europe/Istanbul')
                    dt = turkey_tz.localize(dt)
                    dt = dt.astimezone(timezone.utc)
                elif dt.tzinfo != timezone.utc:
                    # Convert to UTC if it's in a different timezone
                    dt = dt.astimezone(timezone.utc)
                return dt

            # If it's a string, parse it
            if not isinstance(datetime_str, str):
                # Try to convert to string first
                datetime_str = str(datetime_str)

            # First try to parse as ISO format with timezone
            if 'Z' in datetime_str or '+' in datetime_str or datetime_str.endswith('00:00'):
                # Already has timezone info
                return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))

            # Parse as naive datetime
            dt = datetime.fromisoformat(datetime_str)

            # Handle timezone-naive datetime
            if dt.tzinfo is None:
                # For existing reminders, assume they were created in Turkey timezone
                # since the app is primarily used in Turkey
                turkey_tz = pytz.timezone('Europe/Istanbul')
                dt = turkey_tz.localize(dt)
                # Convert to UTC for consistent comparison
                dt = dt.astimezone(timezone.utc)

            return dt

        except Exception as e:
            # Fallback: try to handle as string one more time
            try:
                datetime_str_safe = str(datetime_str)
                dt = datetime.fromisoformat(datetime_str_safe.replace('Z', '+00:00') if 'Z' in datetime_str_safe else datetime_str_safe)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except:
                # Last resort: return current UTC time
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to parse datetime: {datetime_str} (type: {type(datetime_str)}), using current UTC time")
                return datetime.now(timezone.utc)

class Reminder:
    def __init__(self, task_id: str, reminder_time: datetime, message: str, notification: Dict = None,
                 recurrence: str = "none", priority: str = "normal"):
        import uuid
        self.id = str(uuid.uuid4())  # Generate unique ID for reminder
        self.task_id = task_id
        self.reminder_time = reminder_time
        self.message = message
        self.notification = notification or {}  # Friendly notification title and body from Gemini
        self.sent = False
        self.created_at = datetime.now(timezone.utc)
        # New fields for recurrence and priority
        self.recurrence = recurrence  # "none", "daily", "weekly", "monthly"
        self.priority = priority  # "low", "normal", "high"

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "reminder_time": self.reminder_time.isoformat(),
            "message": self.message,
            "notification": self.notification,
            "sent": self.sent,
            "created_at": self.created_at.isoformat(),
            "recurrence": self.recurrence,
            "priority": self.priority
        }