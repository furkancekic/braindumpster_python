import logging
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
from flask import request, jsonify
from functools import wraps

logger = logging.getLogger(__name__)

class APIError(Exception):
    """Base class for API errors"""
    def __init__(self, message: str, status_code: int = 500, error_code: str = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        super().__init__(self.message)

class ValidationError(APIError):
    """Validation error"""
    def __init__(self, message: str, field: str = None):
        self.field = field
        super().__init__(message, 400, 'VALIDATION_ERROR')

class AuthenticationError(APIError):
    """Authentication error"""
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, 401, 'AUTHENTICATION_ERROR')

class AuthorizationError(APIError):
    """Authorization error"""
    def __init__(self, message: str = "Access denied"):
        super().__init__(message, 403, 'AUTHORIZATION_ERROR')

class NotFoundError(APIError):
    """Resource not found error"""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, 404, 'NOT_FOUND_ERROR')

class ConflictError(APIError):
    """Conflict error"""
    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message, 409, 'CONFLICT_ERROR')

class RateLimitError(APIError):
    """Rate limit exceeded error"""
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, 429, 'RATE_LIMIT_ERROR')

class InternalServerError(APIError):
    """Internal server error"""
    def __init__(self, message: str = "Internal server error"):
        super().__init__(message, 500, 'INTERNAL_SERVER_ERROR')

class ExternalServiceError(APIError):
    """External service error"""
    def __init__(self, message: str = "External service error", service: str = None):
        self.service = service
        super().__init__(message, 502, 'EXTERNAL_SERVICE_ERROR')

class SubscriptionError(APIError):
    """Subscription-specific error"""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message, status_code, 'SUBSCRIPTION_ERROR')

class PaymentError(APIError):
    """Payment-specific error"""
    def __init__(self, message: str, status_code: int = 402):
        super().__init__(message, status_code, 'PAYMENT_ERROR')

class RegionalPricingError(APIError):
    """Regional pricing error"""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message, status_code, 'REGIONAL_PRICING_ERROR')

def handle_api_error(error: APIError) -> tuple:
    """Handle API errors and return appropriate response"""
    logger.warning(f"API Error: {error.error_code} - {error.message}")
    
    response_data = {
        'error': error.error_code,
        'message': error.message,
        'timestamp': datetime.utcnow().isoformat(),
        'path': request.path if request else None
    }
    
    # Add field information for validation errors
    if isinstance(error, ValidationError) and hasattr(error, 'field') and error.field:
        response_data['field'] = error.field
    
    # Add service information for external service errors
    if isinstance(error, ExternalServiceError) and hasattr(error, 'service') and error.service:
        response_data['service'] = error.service
    
    return jsonify(response_data), error.status_code

def handle_unexpected_error(error: Exception) -> tuple:
    """Handle unexpected errors"""
    logger.error(f"Unexpected error: {str(error)}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    
    # Log request context for debugging
    if request:
        logger.error(f"Request path: {request.path}")
        logger.error(f"Request method: {request.method}")
        logger.error(f"Request args: {dict(request.args)}")
        
        try:
            if request.is_json:
                logger.error(f"Request data: {request.get_json()}")
        except:
            pass  # Ignore JSON parsing errors during error handling
    
    response_data = {
        'error': 'INTERNAL_SERVER_ERROR',
        'message': 'An unexpected error occurred',
        'timestamp': datetime.utcnow().isoformat(),
        'path': request.path if request else None
    }
    
    # In debug mode, include error details
    # TODO(context7): Only include in development environment
    # if app.debug:
    #     response_data['debug_message'] = str(error)
    #     response_data['debug_traceback'] = traceback.format_exc()
    
    return jsonify(response_data), 500

def error_handler(f):
    """Decorator to handle errors in route functions"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except APIError as e:
            return handle_api_error(e)
        except Exception as e:
            return handle_unexpected_error(e)
    
    return decorated_function

def validate_subscription_access(f):
    """Decorator to validate subscription access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # TODO(context7): Implement subscription access validation
            # This should check if the user has an active subscription
            # for subscription-protected endpoints
            return f(*args, **kwargs)
        except APIError as e:
            return handle_api_error(e)
        except Exception as e:
            return handle_unexpected_error(e)
    
    return decorated_function

def log_error_context(error: Exception, context: Dict[str, Any] = None):
    """Log error with additional context"""
    error_data = {
        'error_type': type(error).__name__,
        'error_message': str(error),
        'timestamp': datetime.utcnow().isoformat(),
    }
    
    if context:
        error_data['context'] = context
    
    if request:
        error_data['request'] = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'args': dict(request.args),
        }
        
        # Add request body for POST/PUT requests (be careful with sensitive data)
        if request.method in ['POST', 'PUT', 'PATCH']:
            try:
                if request.is_json:
                    request_data = request.get_json()
                    # Remove sensitive data before logging
                    if isinstance(request_data, dict):
                        safe_data = {k: v for k, v in request_data.items() 
                                   if k not in ['password', 'token', 'receipt_data', 'secret']}
                        error_data['request']['data'] = safe_data
            except:
                pass  # Ignore JSON parsing errors
    
    logger.error(f"Error context: {error_data}")

class ErrorCollector:
    """Collect and batch errors for reporting"""
    
    def __init__(self):
        self.errors = []
        self.max_errors = 100
    
    def add_error(self, error: Exception, context: Dict[str, Any] = None):
        """Add an error to the collection"""
        error_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'error_type': type(error).__name__,
            'message': str(error),
            'context': context or {}
        }
        
        self.errors.append(error_entry)
        
        # Keep only the most recent errors
        if len(self.errors) > self.max_errors:
            self.errors = self.errors[-self.max_errors:]
    
    def get_errors(self, limit: int = None) -> list:
        """Get collected errors"""
        if limit:
            return self.errors[-limit:]
        return self.errors
    
    def clear_errors(self):
        """Clear collected errors"""
        self.errors.clear()
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of errors"""
        if not self.errors:
            return {'total': 0, 'by_type': {}}
        
        error_counts = {}
        for error in self.errors:
            error_type = error['error_type']
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        
        return {
            'total': len(self.errors),
            'by_type': error_counts,
            'latest': self.errors[-1] if self.errors else None,
            'oldest': self.errors[0] if self.errors else None
        }

# Global error collector instance
error_collector = ErrorCollector()

def safe_execute(func, default_value=None, context: Dict[str, Any] = None):
    """Safely execute a function and return default value on error"""
    try:
        return func()
    except Exception as e:
        log_error_context(e, context)
        error_collector.add_error(e, context)
        return default_value

def retry_with_backoff(func, max_retries: int = 3, backoff_factor: float = 1.0):
    """Retry a function with exponential backoff"""
    import time
    
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                # Last attempt failed, re-raise the exception
                raise e
            
            # Wait before retrying
            wait_time = backoff_factor * (2 ** attempt)
            logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s: {str(e)}")
            time.sleep(wait_time)
    
    return None  # Should never reach here

def create_error_response(message: str, error_code: str = None, status_code: int = 400, **kwargs) -> tuple:
    """Create a standardized error response"""
    response_data = {
        'error': error_code or 'API_ERROR',
        'message': message,
        'timestamp': datetime.utcnow().isoformat(),
        'path': request.path if request else None
    }
    
    # Add any additional data
    response_data.update(kwargs)
    
    return jsonify(response_data), status_code