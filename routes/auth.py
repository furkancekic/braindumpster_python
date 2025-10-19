from flask import Blueprint, request, jsonify, current_app
from services.firebase_service import FirebaseService
from models.user import User
from functools import wraps

auth_bp = Blueprint('auth', __name__)

def require_auth(f):
    """Decorator to require authentication for endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Authorization required"}), 401
        
        # Extract token
        id_token = auth_header.split('Bearer ')[1]
        
        # Verify token with Firebase
        firebase_service = current_app.firebase_service
        decoded_token = firebase_service.verify_id_token(id_token)
        
        if not decoded_token:
            return jsonify({"error": "Invalid or expired token"}), 401
        
        # Add user info to request
        request.user_id = decoded_token.get('uid')
        request.user_email = decoded_token.get('email')
        
        return f(*args, **kwargs)
    
    return decorated_function

@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        display_name = data.get('display_name')
        timezone = data.get('timezone', 'UTC')  # Default to UTC if not provided
        
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400
        
        firebase_service = current_app.firebase_service
        result = firebase_service.create_user(email, password, display_name, timezone)
        
        if result["success"]:
            return jsonify({
                "message": "User created successfully",
                "uid": result["uid"]
            }), 201
        else:
            return jsonify({"error": result["error"]}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route('/verify', methods=['POST'])
def verify_token():
    try:
        data = request.get_json()
        id_token = data.get('id_token')
        
        if not id_token:
            return jsonify({"error": "ID token is required"}), 400
        
        firebase_service = current_app.firebase_service
        decoded_token = firebase_service.verify_id_token(id_token)
        
        if decoded_token:
            return jsonify({
                "valid": True,
                "uid": decoded_token["uid"],
                "email": decoded_token.get("email")
            })
        else:
            return jsonify({"valid": False}), 401
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route('/profile/<user_id>', methods=['GET'])
@require_auth
def get_profile(user_id):
    try:
        # Security: Ensure user can only access their own profile
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized: Cannot access another user's profile"}), 403
            
        firebase_service = current_app.firebase_service
        context = firebase_service.get_user_context(user_id)
        
        return jsonify({
            "profile": context.get("user_profile", {}),
            "preferences": context.get("user_preferences", {}),
            "stats": {
                "total_tasks": len(context.get("recent_tasks", [])),
                "completed_tasks": len([t for t in context.get("recent_tasks", []) if t.get("status") == "completed"]),
                "conversations": len(context.get("conversation_history", []))
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route('/profile/<user_id>/timezone', methods=['PUT'])
@require_auth
def update_user_timezone(user_id):
    """Update user's timezone preference"""
    try:
        # Security: Ensure user can only update their own timezone
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized: Cannot update another user's timezone"}), 403
        
        data = request.get_json()
        timezone = data.get('timezone')
        
        if not timezone:
            return jsonify({"error": "Timezone is required"}), 400
        
        # Validate timezone format
        try:
            import pytz
            pytz.timezone(timezone)  # This will raise an exception if invalid
        except Exception:
            return jsonify({"error": "Invalid timezone format"}), 400
        
        firebase_service = current_app.firebase_service
        
        # Update user's timezone preference
        updates = {
            "preferences.timezone": timezone
        }
        
        firebase_service.db.collection('users').document(user_id).update(updates)
        
        return jsonify({
            "message": "Timezone updated successfully",
            "timezone": timezone
        }), 200
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500