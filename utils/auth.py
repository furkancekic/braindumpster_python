"""
Authentication utilities for the Braindumpster API.
Provides standardized authentication patterns across all endpoints.
"""

import logging
from functools import wraps
from flask import request, jsonify, current_app
from typing import Callable, Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class AuthenticationError(Exception):
    """Custom exception for authentication-related errors."""
    
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class AuthorizationError(Exception):
    """Custom exception for authorization-related errors."""
    
    def __init__(self, message: str, status_code: int = 403):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class AuthManager:
    """Centralized authentication and authorization management."""
    
    @staticmethod
    def extract_token_from_header(auth_header: Optional[str]) -> str:
        """
        Extracts the JWT token from the Authorization header.
        
        Args:
            auth_header: The Authorization header value
            
        Returns:
            str: The extracted JWT token
            
        Raises:
            AuthenticationError: If header is missing or invalid
        """
        if not auth_header:
            raise AuthenticationError("Authorization header is missing")
        
        if not auth_header.startswith('Bearer '):
            raise AuthenticationError("Authorization header must start with 'Bearer '")
        
        try:
            token = auth_header.split('Bearer ')[1]
            if not token:
                raise AuthenticationError("Token is empty")
            return token
        except IndexError:
            raise AuthenticationError("Invalid Authorization header format")
    
    @staticmethod
    def verify_token(token: str) -> Dict[str, Any]:
        """
        Verifies a JWT token using Firebase.
        
        Args:
            token: The JWT token to verify
            
        Returns:
            Dict: Decoded token data containing user information
            
        Raises:
            AuthenticationError: If token is invalid or expired
        """
        try:
            firebase_service = current_app.firebase_service
            if not firebase_service:
                logger.error("Firebase service not available")
                raise AuthenticationError("Authentication service unavailable")
            
            decoded_token = firebase_service.verify_id_token(token)
            
            if not decoded_token:
                raise AuthenticationError("Invalid or expired token")
            
            # Validate required fields in token
            if 'uid' not in decoded_token:
                raise AuthenticationError("Token missing user ID")
            
            logger.debug(f"Token verified successfully for user: {decoded_token.get('uid')}")
            return decoded_token
            
        except Exception as e:
            if isinstance(e, AuthenticationError):
                raise
            logger.error(f"Token verification failed: {str(e)}")
            raise AuthenticationError("Token verification failed")
    
    @staticmethod
    def authenticate_request() -> Tuple[str, str, str]:
        """
        Authenticates the current request and returns user information.
        
        Returns:
            Tuple: (user_id, user_email, user_timezone)
            
        Raises:
            AuthenticationError: If authentication fails
        """
        # Extract token from Authorization header
        auth_header = request.headers.get('Authorization')
        token = AuthManager.extract_token_from_header(auth_header)
        
        # Verify token
        decoded_token = AuthManager.verify_token(token)
        
        # Extract user information
        user_id = decoded_token.get('uid')
        user_email = decoded_token.get('email')
        
        # Extract timezone from headers (optional)
        user_timezone = request.headers.get('X-User-Timezone', 'UTC')
        
        if not user_id:
            raise AuthenticationError("Token missing user ID")
        
        logger.info(f"Request authenticated for user: {user_email} ({user_id}) with timezone: {user_timezone}")
        return user_id, user_email, user_timezone
    
    @staticmethod
    def authorize_user_access(authenticated_user_id: str, target_user_id: str) -> None:
        """
        Validates that a user can only access their own resources.
        
        Args:
            authenticated_user_id: User ID from the authentication token
            target_user_id: User ID being accessed
            
        Raises:
            AuthorizationError: If user tries to access another user's resources
        """
        if not authenticated_user_id:
            raise AuthorizationError("Authentication failed: user_id not found")
        
        if authenticated_user_id != target_user_id:
            logger.warning(
                f"Unauthorized access attempt: {authenticated_user_id} "
                f"tried to access {target_user_id}'s resources"
            )
            raise AuthorizationError("Cannot access another user's resources")
        
        logger.debug(f"User access authorized: {authenticated_user_id}")

def require_auth(f: Callable) -> Callable:
    """
    Decorator that requires authentication for endpoints.
    
    This decorator:
    1. Extracts and verifies the JWT token
    2. Adds user_id and user_email to the request object
    3. Provides consistent error handling
    
    Usage:
        @app.route('/protected')
        @require_auth
        def protected_endpoint():
            user_id = request.user_id
            user_email = request.user_email
            # ... endpoint logic
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # Authenticate the request
            user_id, user_email, user_timezone = AuthManager.authenticate_request()
            
            # Add user info to request object
            request.user_id = user_id
            request.user_email = user_email
            request.user_timezone = user_timezone
            
            # Call the original function
            return f(*args, **kwargs)
            
        except AuthenticationError as e:
            logger.warning(f"Authentication failed: {e.message}")
            return jsonify({
                "error": e.message,
                "type": "authentication_error"
            }), e.status_code
        except AuthorizationError as e:
            logger.warning(f"Authorization failed: {e.message}")
            return jsonify({
                "error": e.message,
                "type": "authorization_error"
            }), e.status_code
        except Exception as e:
            logger.error(f"Unexpected error in authentication: {str(e)}")
            return jsonify({
                "error": "Authentication failed",
                "type": "authentication_error"
            }), 500
    
    return decorated_function

def require_user_access(user_id_param: str = None) -> Callable:
    """
    Decorator that requires authentication and validates user access.
    
    This decorator combines authentication with user access validation.
    It ensures that users can only access their own resources.
    
    Args:
        user_id_param: Name of the parameter containing the user ID to validate.
                      If None, no access validation is performed.
    
    Usage:
        @app.route('/user/<user_id>/data')
        @require_user_access('user_id')
        def get_user_data(user_id):
            # This endpoint ensures user can only access their own data
            pass
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # Authenticate the request
                user_id, user_email, user_timezone = AuthManager.authenticate_request()
                
                # Add user info to request object
                request.user_id = user_id
                request.user_email = user_email
                request.user_timezone = user_timezone
                
                # Validate user access if parameter is specified
                if user_id_param:
                    # Get the target user ID from function parameters
                    target_user_id = kwargs.get(user_id_param)
                    if not target_user_id:
                        # Try to get from request data
                        data = request.get_json() or {}
                        target_user_id = data.get(user_id_param)
                    
                    if target_user_id:
                        AuthManager.authorize_user_access(user_id, target_user_id)
                
                # Call the original function
                return f(*args, **kwargs)
                
            except AuthenticationError as e:
                logger.warning(f"Authentication failed: {e.message}")
                return jsonify({
                    "error": e.message,
                    "type": "authentication_error"
                }), e.status_code
            except AuthorizationError as e:
                logger.warning(f"Authorization failed: {e.message}")
                return jsonify({
                    "error": e.message,
                    "type": "authorization_error"
                }), e.status_code
            except Exception as e:
                logger.error(f"Unexpected error in authentication: {str(e)}")
                return jsonify({
                    "error": "Authentication failed",
                    "type": "authentication_error"
                }), 500
        
        return decorated_function
    return decorator

def validate_user_access_in_request(request_user_id: str, data: Dict[str, Any], 
                                   user_id_field: str = 'user_id') -> None:
    """
    Validates that a user can only access their own resources based on request data.
    
    Args:
        request_user_id: User ID from the authentication token
        data: Request data dictionary
        user_id_field: Name of the field containing the user ID
        
    Raises:
        AuthorizationError: If user tries to access another user's resources
    """
    target_user_id = data.get(user_id_field)
    if target_user_id:
        AuthManager.authorize_user_access(request_user_id, target_user_id)

# Utility functions for manual authentication (for endpoints that need custom logic)
def get_authenticated_user() -> Tuple[str, str, str]:
    """
    Gets the authenticated user information from the current request.
    
    Returns:
        Tuple: (user_id, user_email, user_timezone)
        
    Raises:
        AuthenticationError: If authentication fails
    """
    return AuthManager.authenticate_request()

def check_user_access(authenticated_user_id: str, target_user_id: str) -> None:
    """
    Checks if a user can access a specific user's resources.
    
    Args:
        authenticated_user_id: User ID from the authentication token
        target_user_id: User ID being accessed
        
    Raises:
        AuthorizationError: If user tries to access another user's resources
    """
    AuthManager.authorize_user_access(authenticated_user_id, target_user_id)

# Health check utilities
def check_auth_service_health() -> Dict[str, Any]:
    """
    Checks the health of the authentication service.
    
    Returns:
        Dict: Health check results
    """
    try:
        firebase_service = current_app.firebase_service
        if not firebase_service:
            return {
                "status": "unhealthy",
                "message": "Firebase service not available"
            }
        
        # Try to perform a basic health check
        health_status = firebase_service.health_check()
        
        return {
            "status": "healthy" if health_status else "unhealthy",
            "message": "Authentication service operational" if health_status else "Firebase service unavailable"
        }
    except Exception as e:
        logger.error(f"Auth service health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "message": f"Health check failed: {str(e)}"
        }