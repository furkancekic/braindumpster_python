from typing import Dict, Any, List, Union
import re
import logging

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Custom exception for validation errors"""
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(self.message)

def validate_json_data(data: Dict[str, Any], schema: Dict[str, Dict]) -> Dict[str, Any]:
    """
    Validate JSON data against a schema
    
    Schema format:
    {
        'field_name': {
            'type': 'string|int|float|bool|dict|list',
            'required': True|False,
            'allowed': [list of allowed values],
            'min_length': int,
            'max_length': int,
            'pattern': 'regex pattern',
            'min_value': number,
            'max_value': number
        }
    }
    """
    if not isinstance(data, dict):
        raise ValidationError("Data must be a dictionary")
    
    validated_data = {}
    
    # Check required fields and validate types
    for field_name, field_config in schema.items():
        value = data.get(field_name)
        
        # Check if field is required
        if field_config.get('required', False) and value is None:
            raise ValidationError(f"Field '{field_name}' is required", field_name)
        
        # Skip validation for optional fields that are None
        if value is None and not field_config.get('required', False):
            continue
        
        # Validate type
        expected_type = field_config.get('type')
        if expected_type and not _validate_type(value, expected_type):
            raise ValidationError(f"Field '{field_name}' must be of type {expected_type}", field_name)
        
        # Validate allowed values
        allowed_values = field_config.get('allowed')
        if allowed_values and value not in allowed_values:
            raise ValidationError(f"Field '{field_name}' must be one of {allowed_values}", field_name)
        
        # Validate string length
        if isinstance(value, str):
            min_length = field_config.get('min_length')
            max_length = field_config.get('max_length')
            
            if min_length and len(value) < min_length:
                raise ValidationError(f"Field '{field_name}' must be at least {min_length} characters long", field_name)
            
            if max_length and len(value) > max_length:
                raise ValidationError(f"Field '{field_name}' must be at most {max_length} characters long", field_name)
            
            # Validate pattern
            pattern = field_config.get('pattern')
            if pattern and not re.match(pattern, value):
                raise ValidationError(f"Field '{field_name}' does not match required pattern", field_name)
        
        # Validate numeric values
        if isinstance(value, (int, float)):
            min_value = field_config.get('min_value')
            max_value = field_config.get('max_value')
            
            if min_value is not None and value < min_value:
                raise ValidationError(f"Field '{field_name}' must be at least {min_value}", field_name)
            
            if max_value is not None and value > max_value:
                raise ValidationError(f"Field '{field_name}' must be at most {max_value}", field_name)
        
        validated_data[field_name] = value
    
    return validated_data

def _validate_type(value: Any, expected_type: str) -> bool:
    """Validate if a value matches the expected type"""
    type_mapping = {
        'string': str,
        'int': int,
        'integer': int,
        'float': (int, float),  # Accept both int and float for float fields
        'number': (int, float),
        'bool': bool,
        'boolean': bool,
        'dict': dict,
        'object': dict,
        'list': list,
        'array': list,
    }
    
    expected_python_type = type_mapping.get(expected_type.lower())
    if not expected_python_type:
        logger.warning(f"Unknown type: {expected_type}")
        return True  # Allow unknown types
    
    return isinstance(value, expected_python_type)

def validate_email(email: str) -> bool:
    """Validate email address format"""
    if not isinstance(email, str):
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email.strip()) is not None

def validate_user_id(user_id: str) -> bool:
    """Validate Firebase user ID format"""
    if not isinstance(user_id, str):
        return False
    
    # Firebase user IDs are typically 28 characters long
    return len(user_id.strip()) >= 10 and len(user_id.strip()) <= 50

def validate_transaction_id(transaction_id: str) -> bool:
    """Validate transaction ID format"""
    if not isinstance(transaction_id, str):
        return False
    
    # Transaction IDs should be non-empty strings
    return len(transaction_id.strip()) > 0

def validate_country_code(country_code: str) -> bool:
    """Validate ISO 3166-1 alpha-2 country code"""
    if not isinstance(country_code, str):
        return False
    
    # ISO 3166-1 alpha-2 codes are exactly 2 characters
    return len(country_code.strip().upper()) == 2 and country_code.isalpha()

def validate_currency_code(currency_code: str) -> bool:
    """Validate ISO 4217 currency code"""
    if not isinstance(currency_code, str):
        return False
    
    # ISO 4217 codes are exactly 3 characters
    return len(currency_code.strip().upper()) == 3 and currency_code.isalpha()

def validate_product_id(product_id: str) -> bool:
    """Validate product ID format"""
    if not isinstance(product_id, str):
        return False
    
    # Product IDs should be non-empty and contain only alphanumeric characters, underscores, and dots
    pattern = r'^[a-zA-Z0-9._-]+$'
    return len(product_id.strip()) > 0 and re.match(pattern, product_id.strip())

def validate_price(price: Union[int, float]) -> bool:
    """Validate price value"""
    if not isinstance(price, (int, float)):
        return False
    
    # Price should be positive
    return price >= 0

def sanitize_string(value: str, max_length: int = None) -> str:
    """Sanitize string input"""
    if not isinstance(value, str):
        return str(value)
    
    # Strip whitespace
    sanitized = value.strip()
    
    # Limit length if specified
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized

def validate_subscription_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate subscription-specific data"""
    schema = {
        'user_id': {
            'type': 'string',
            'required': True,
            'min_length': 10,
            'max_length': 50
        },
        'tier': {
            'type': 'string',
            'required': True,
            'allowed': ['monthly_premium', 'yearly_premium', 'lifetime_premium']
        },
        'status': {
            'type': 'string',
            'required': True,
            'allowed': ['active', 'expired', 'cancelled', 'pending', 'grace_period', 'billing_issue']
        },
        'transaction_id': {
            'type': 'string',
            'required': False,
            'min_length': 1
        },
        'platform': {
            'type': 'string',
            'required': False,
            'allowed': ['ios', 'android', 'flutter', 'web', 'revenuecat']
        },
        'price': {
            'type': 'float',
            'required': False,
            'min_value': 0
        },
        'currency': {
            'type': 'string',
            'required': False,
            'min_length': 3,
            'max_length': 3
        }
    }
    
    return validate_json_data(data, schema)

def validate_analytics_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate analytics event data"""
    schema = {
        'user_id': {
            'type': 'string',
            'required': True,
            'min_length': 10,
            'max_length': 50
        },
        'event': {
            'type': 'string',
            'required': True,
            'min_length': 1,
            'max_length': 100
        },
        'timestamp': {
            'type': 'string',
            'required': False
        },
        'platform': {
            'type': 'string',
            'required': False,
            'allowed': ['ios', 'android', 'flutter', 'web']
        }
    }
    
    return validate_json_data(data, schema)

class FieldValidator:
    """Utility class for field-specific validation"""
    
    @staticmethod
    def required(value: Any, field_name: str = "field") -> Any:
        """Check if required field has a value"""
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationError(f"{field_name} is required")
        return value
    
    @staticmethod
    def email(value: str, field_name: str = "email") -> str:
        """Validate email field"""
        if not validate_email(value):
            raise ValidationError(f"{field_name} must be a valid email address")
        return value.strip().lower()
    
    @staticmethod
    def user_id(value: str, field_name: str = "user_id") -> str:
        """Validate user ID field"""
        if not validate_user_id(value):
            raise ValidationError(f"{field_name} must be a valid user ID")
        return value.strip()
    
    @staticmethod
    def country_code(value: str, field_name: str = "country_code") -> str:
        """Validate country code field"""
        if not validate_country_code(value):
            raise ValidationError(f"{field_name} must be a valid 2-letter country code")
        return value.strip().upper()
    
    @staticmethod
    def currency_code(value: str, field_name: str = "currency_code") -> str:
        """Validate currency code field"""
        if not validate_currency_code(value):
            raise ValidationError(f"{field_name} must be a valid 3-letter currency code")
        return value.strip().upper()
    
    @staticmethod
    def positive_number(value: Union[int, float], field_name: str = "value") -> Union[int, float]:
        """Validate positive number"""
        if not isinstance(value, (int, float)) or value <= 0:
            raise ValidationError(f"{field_name} must be a positive number")
        return value
    
    @staticmethod
    def non_negative_number(value: Union[int, float], field_name: str = "value") -> Union[int, float]:
        """Validate non-negative number"""
        if not isinstance(value, (int, float)) or value < 0:
            raise ValidationError(f"{field_name} must be a non-negative number")
        return value