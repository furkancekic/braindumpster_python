"""
Comprehensive validation utilities for the Braindumpster API.
Provides consistent validation patterns and error handling across all endpoints.
"""

import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Tuple
from enum import Enum
from models.task import TaskPriority, TaskStatus

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Custom exception for validation errors with detailed information."""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Any = None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(message)

class DateFormatValidator:
    """Validates and normalizes date formats."""
    
    @staticmethod
    def validate_and_parse_date(date_str: Union[str, datetime], field_name: str = "date") -> datetime:
        """
        Validates and parses date strings with various formats.
        
        Args:
            date_str: The date string or datetime object to validate
            field_name: Name of the field being validated (for error messages)
            
        Returns:
            datetime: Parsed datetime object
            
        Raises:
            ValidationError: If date format is invalid
        """
        if not date_str:
            raise ValidationError(f"{field_name} cannot be empty", field_name, date_str)
        
        if isinstance(date_str, datetime):
            return date_str
        
        if not isinstance(date_str, str):
            raise ValidationError(f"{field_name} must be a string or datetime object", field_name, date_str)
        
        # Handle various date formats
        try:
            # Remove 'Z' suffix and replace with '+00:00' for proper ISO format
            normalized_date = date_str
            if normalized_date.endswith('Z'):
                normalized_date = normalized_date[:-1] + '+00:00'
            
            # Try to parse as ISO format
            parsed_date = datetime.fromisoformat(normalized_date)
            logger.debug(f"Successfully parsed {field_name}: {date_str} -> {parsed_date}")
            return parsed_date
            
        except ValueError as e:
            logger.error(f"Failed to parse {field_name} '{date_str}': {e}")
            raise ValidationError(
                f"Invalid {field_name} format: {date_str}. Expected ISO format (YYYY-MM-DDTHH:MM:SS)", 
                field_name, 
                date_str
            )

class EnumValidator:
    """Handles validation and mapping for enumerated values."""
    
    # Priority mapping
    PRIORITY_MAPPING = {
        'low': TaskPriority.LOW,
        'medium': TaskPriority.MEDIUM,
        'high': TaskPriority.HIGH,
        'urgent': TaskPriority.URGENT
    }
    
    # Status mapping
    STATUS_MAPPING = {
        'pending': TaskStatus.PENDING,
        'approved': TaskStatus.APPROVED,
        'completed': TaskStatus.COMPLETED,
        'cancelled': TaskStatus.CANCELLED
    }
    
    @staticmethod
    def validate_priority(priority_str: str, field_name: str = "priority") -> TaskPriority:
        """
        Validates and converts priority string to TaskPriority enum.
        
        Args:
            priority_str: Priority string
            field_name: Name of the field being validated
            
        Returns:
            TaskPriority: The validated priority enum
            
        Raises:
            ValidationError: If priority is invalid
        """
        if not priority_str:
            logger.info(f"Empty {field_name}, defaulting to MEDIUM")
            return TaskPriority.MEDIUM
        
        if not isinstance(priority_str, str):
            raise ValidationError(f"{field_name} must be a string", field_name, priority_str)
        
        priority_lower = priority_str.lower().strip()
        
        if priority_lower in EnumValidator.PRIORITY_MAPPING:
            result = EnumValidator.PRIORITY_MAPPING[priority_lower]
            logger.debug(f"Validated {field_name}: {priority_str} -> {result}")
            return result
        
        # Try direct enum conversion as fallback
        try:
            result = TaskPriority(priority_lower)
            logger.debug(f"Direct enum conversion for {field_name}: {priority_str} -> {result}")
            return result
        except ValueError:
            pass
        
        logger.warning(f"Invalid {field_name} '{priority_str}', defaulting to MEDIUM")
        return TaskPriority.MEDIUM
    
    @staticmethod
    def validate_status(status_str: str, field_name: str = "status") -> TaskStatus:
        """
        Validates and converts status string to TaskStatus enum.
        
        Args:
            status_str: Status string
            field_name: Name of the field being validated
            
        Returns:
            TaskStatus: The validated status enum
            
        Raises:
            ValidationError: If status is invalid
        """
        if not status_str:
            raise ValidationError(f"{field_name} cannot be empty", field_name, status_str)
        
        if not isinstance(status_str, str):
            raise ValidationError(f"{field_name} must be a string", field_name, status_str)
        
        status_lower = status_str.lower().strip()
        
        if status_lower in EnumValidator.STATUS_MAPPING:
            result = EnumValidator.STATUS_MAPPING[status_lower]
            logger.debug(f"Validated {field_name}: {status_str} -> {result}")
            return result
        
        # Try direct enum conversion as fallback
        try:
            result = TaskStatus(status_lower)
            logger.debug(f"Direct enum conversion for {field_name}: {status_str} -> {result}")
            return result
        except ValueError:
            pass
        
        # List valid options in error message
        valid_options = list(EnumValidator.STATUS_MAPPING.keys())
        raise ValidationError(
            f"Invalid {field_name} '{status_str}'. Valid options: {valid_options}", 
            field_name, 
            status_str
        )

class RequestValidator:
    """Validates common request patterns."""
    
    @staticmethod
    def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> None:
        """
        Validates that all required fields are present in the request data.
        
        Args:
            data: Request data dictionary
            required_fields: List of required field names
            
        Raises:
            ValidationError: If any required field is missing
        """
        if not data:
            raise ValidationError("Request body cannot be empty")
        
        missing_fields = []
        for field in required_fields:
            if field not in data or data[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")
        
        logger.debug(f"All required fields present: {required_fields}")
    
    @staticmethod
    def validate_string_field(data: Dict[str, Any], field_name: str, required: bool = True, 
                             min_length: int = 1, max_length: int = 1000) -> Optional[str]:
        """
        Validates a string field with length constraints.
        
        Args:
            data: Request data dictionary
            field_name: Name of the field to validate
            required: Whether the field is required
            min_length: Minimum string length
            max_length: Maximum string length
            
        Returns:
            str or None: The validated string value
            
        Raises:
            ValidationError: If validation fails
        """
        value = data.get(field_name)
        
        if not value:
            if required:
                raise ValidationError(f"{field_name} is required", field_name)
            return None
        
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string", field_name, value)
        
        value = value.strip()
        
        if len(value) < min_length:
            raise ValidationError(f"{field_name} must be at least {min_length} characters long", field_name, value)
        
        if len(value) > max_length:
            raise ValidationError(f"{field_name} must be no more than {max_length} characters long", field_name, value)
        
        logger.debug(f"Validated string field {field_name}: length={len(value)}")
        return value
    
    @staticmethod
    def validate_list_field(data: Dict[str, Any], field_name: str, required: bool = True, 
                           min_items: int = 0, max_items: int = 100) -> Optional[List[Any]]:
        """
        Validates a list field with size constraints.
        
        Args:
            data: Request data dictionary
            field_name: Name of the field to validate
            required: Whether the field is required
            min_items: Minimum number of items
            max_items: Maximum number of items
            
        Returns:
            List or None: The validated list value
            
        Raises:
            ValidationError: If validation fails
        """
        value = data.get(field_name)
        
        if not value:
            if required:
                raise ValidationError(f"{field_name} is required", field_name)
            return None
        
        if not isinstance(value, list):
            raise ValidationError(f"{field_name} must be a list", field_name, value)
        
        if len(value) < min_items:
            raise ValidationError(f"{field_name} must have at least {min_items} items", field_name, value)
        
        if len(value) > max_items:
            raise ValidationError(f"{field_name} must have no more than {max_items} items", field_name, value)
        
        logger.debug(f"Validated list field {field_name}: length={len(value)}")
        return value
    
    @staticmethod
    def validate_user_access(request_user_id: str, target_user_id: str) -> None:
        """
        Validates that a user can only access their own resources.
        
        Args:
            request_user_id: User ID from the authentication token
            target_user_id: User ID being accessed
            
        Raises:
            ValidationError: If user tries to access another user's resources
        """
        if not request_user_id:
            raise ValidationError("Authentication failed: user_id not found in token")
        
        if request_user_id != target_user_id:
            logger.warning(f"Unauthorized access attempt: {request_user_id} tried to access {target_user_id}'s resources")
            raise ValidationError("Unauthorized: Cannot access another user's resources")
        
        logger.debug(f"User access validated: {request_user_id}")

class TaskValidator:
    """Specialized validator for task-related data."""
    
    @staticmethod
    def validate_task_data(task_data: Dict[str, Any], task_index: int = 0) -> Dict[str, Any]:
        """
        Validates a single task data structure.
        
        Args:
            task_data: Task data dictionary
            task_index: Index of the task (for error messages)
            
        Returns:
            Dict: Validated task data
            
        Raises:
            ValidationError: If validation fails
        """
        if not task_data:
            raise ValidationError(f"Task {task_index + 1} data cannot be empty")
        
        validated_data = {}
        
        # Validate required fields
        validated_data['title'] = RequestValidator.validate_string_field(
            task_data, 'title', required=True, min_length=1, max_length=200
        )
        
        validated_data['description'] = RequestValidator.validate_string_field(
            task_data, 'description', required=True, min_length=1, max_length=2000
        )
        
        # Validate optional fields
        if 'due_date' in task_data and task_data['due_date']:
            validated_data['due_date'] = DateFormatValidator.validate_and_parse_date(
                task_data['due_date'], f'due_date for task {task_index + 1}'
            )
        
        # Validate priority
        priority_str = task_data.get('priority', 'medium')
        validated_data['priority'] = EnumValidator.validate_priority(
            priority_str, f'priority for task {task_index + 1}'
        )
        
        # Validate subtasks if present
        if 'subtasks' in task_data and task_data['subtasks']:
            validated_data['subtasks'] = RequestValidator.validate_list_field(
                task_data, 'subtasks', required=False, max_items=50
            )
        
        # Validate reminders if present
        if 'reminders' in task_data and task_data['reminders']:
            validated_data['reminders'] = TaskValidator.validate_reminders(
                task_data['reminders'], task_index
            )

        # Validate recurring fields
        if 'is_recurring' in task_data:
            is_recurring = task_data['is_recurring']
            if not isinstance(is_recurring, bool):
                raise ValidationError(f"is_recurring for task {task_index + 1} must be a boolean")
            validated_data['is_recurring'] = is_recurring

        if 'recurring_pattern' in task_data:
            recurring_pattern = task_data['recurring_pattern']
            if not isinstance(recurring_pattern, dict):
                raise ValidationError(f"recurring_pattern for task {task_index + 1} must be a dictionary")
            validated_data['recurring_pattern'] = recurring_pattern

        logger.debug(f"Task {task_index + 1} validation completed: {validated_data['title']}")
        return validated_data
    
    @staticmethod
    def validate_reminders(reminders_data: List[Dict[str, Any]], task_index: int) -> List[Dict[str, Any]]:
        """
        Validates reminder data for a task.
        
        Args:
            reminders_data: List of reminder dictionaries
            task_index: Index of the parent task
            
        Returns:
            List: Validated reminder data
            
        Raises:
            ValidationError: If validation fails
        """
        if not isinstance(reminders_data, list):
            raise ValidationError(f"Reminders for task {task_index + 1} must be a list")
        
        if len(reminders_data) > 500:
            raise ValidationError(f"Task {task_index + 1} can have at most 500 reminders")
        
        validated_reminders = []
        
        for i, reminder_data in enumerate(reminders_data):
            if not reminder_data:
                raise ValidationError(f"Reminder {i + 1} for task {task_index + 1} cannot be empty")
            
            validated_reminder = {}
            
            # Validate reminder_time
            if 'reminder_time' not in reminder_data:
                raise ValidationError(f"Reminder {i + 1} for task {task_index + 1} missing reminder_time")
            
            validated_reminder['reminder_time'] = DateFormatValidator.validate_and_parse_date(
                reminder_data['reminder_time'], 
                f'reminder_time for reminder {i + 1} of task {task_index + 1}'
            )
            
            # Validate message
            validated_reminder['message'] = RequestValidator.validate_string_field(
                reminder_data, 'message', required=True, min_length=1, max_length=500
            )
            
            validated_reminders.append(validated_reminder)
        
        logger.debug(f"Validated {len(validated_reminders)} reminders for task {task_index + 1}")
        return validated_reminders

# Error response utilities
def create_validation_error_response(error: ValidationError) -> Tuple[Dict[str, Any], int]:
    """
    Creates a standardized error response for validation errors.
    
    Args:
        error: ValidationError instance
        
    Returns:
        Tuple: (response_dict, status_code)
    """
    response = {
        "error": error.message,
        "type": "validation_error"
    }
    
    if error.field:
        response["field"] = error.field
    
    if error.value is not None:
        response["invalid_value"] = str(error.value)
    
    logger.error(f"Validation error: {error.message} (field: {error.field}, value: {error.value})")
    return response, 400

def create_auth_error_response(message: str = "Authentication required") -> Tuple[Dict[str, Any], int]:
    """
    Creates a standardized error response for authentication errors.
    
    Args:
        message: Error message
        
    Returns:
        Tuple: (response_dict, status_code)
    """
    response = {
        "error": message,
        "type": "authentication_error"
    }
    
    logger.warning(f"Authentication error: {message}")
    return response, 401

def create_authorization_error_response(message: str = "Unauthorized access") -> Tuple[Dict[str, Any], int]:
    """
    Creates a standardized error response for authorization errors.
    
    Args:
        message: Error message
        
    Returns:
        Tuple: (response_dict, status_code)
    """
    response = {
        "error": message,
        "type": "authorization_error"
    }
    
    logger.warning(f"Authorization error: {message}")
    return response, 403