from functools import wraps
from flask import request, jsonify, g
import firebase_admin
from firebase_admin import auth
import logging

logger = logging.getLogger(__name__)

def require_auth(f):
    """Decorator to require Firebase authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get the Authorization header
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'error': 'Authorization header is required'}), 401
        
        try:
            # Extract the token from "Bearer <token>"
            if not auth_header.startswith('Bearer '):
                return jsonify({'error': 'Invalid authorization header format'}), 401
            
            id_token = auth_header.split('Bearer ')[1]
            
            # Verify the ID token
            decoded_token = auth.verify_id_token(id_token)
            
            # Store user info in g for use in the route
            g.user_id = decoded_token['uid']
            g.user_email = decoded_token.get('email')
            g.user = decoded_token
            
            logger.info(f"Authenticated user: {g.user_id}")
            
            return f(*args, **kwargs)
            
        except ValueError as e:
            logger.error(f"Token verification failed: {e}")
            return jsonify({'error': 'Invalid token'}), 401
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return jsonify({'error': 'Authentication failed'}), 401
    
    return decorated_function

def get_current_user():
    """Get the current authenticated user from g"""
    return getattr(g, 'user', None)

def get_current_user_id():
    """Get the current authenticated user ID from g"""
    return getattr(g, 'user_id', None)

def get_current_user_email():
    """Get the current authenticated user email from g"""
    return getattr(g, 'user_email', None)

def optional_auth(f):
    """Decorator for optional authentication (user info available if token provided)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get the Authorization header
        auth_header = request.headers.get('Authorization')
        
        if auth_header and auth_header.startswith('Bearer '):
            try:
                id_token = auth_header.split('Bearer ')[1]
                decoded_token = auth.verify_id_token(id_token)
                
                # Store user info in g
                g.user_id = decoded_token['uid']
                g.user_email = decoded_token.get('email')
                g.user = decoded_token
                
                logger.info(f"Optional auth - authenticated user: {g.user_id}")
                
            except Exception as e:
                logger.warning(f"Optional auth failed, continuing without user: {e}")
                g.user_id = None
                g.user_email = None
                g.user = None
        else:
            g.user_id = None
            g.user_email = None
            g.user = None
        
        return f(*args, **kwargs)
    
    return decorated_function

def verify_token_only(token: str) -> dict:
    """Verify a Firebase ID token and return user info"""
    try:
        decoded_token = auth.verify_id_token(token)
        return {
            'success': True,
            'user_id': decoded_token['uid'],
            'email': decoded_token.get('email'),
            'user_data': decoded_token
        }
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def require_user_match(user_id_param='user_id'):
    """Decorator to ensure the authenticated user matches the requested user_id"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            current_user_id = get_current_user_id()
            
            if not current_user_id:
                return jsonify({'error': 'Authentication required'}), 401
            
            # Get user_id from request
            if request.method == 'GET':
                requested_user_id = request.args.get(user_id_param)
            else:
                data = request.get_json() or {}
                requested_user_id = data.get(user_id_param)
            
            if not requested_user_id:
                return jsonify({'error': f'{user_id_param} is required'}), 400
            
            # Ensure user can only access their own data
            if current_user_id != requested_user_id:
                return jsonify({'error': 'Access denied'}), 403
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user = get_current_user()
        
        if not current_user:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Check if user has admin claims
        if not current_user.get('admin', False):
            return jsonify({'error': 'Admin privileges required'}), 403
        
        return f(*args, **kwargs)
    
    return decorated_function