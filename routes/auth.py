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

@auth_bp.route('/ensure-user', methods=['POST'])
@require_auth
def ensure_user():
    """
    Ensure user document exists in Firestore (iOS compatible)
    Called after Google Sign-In or other OAuth providers
    Idempotent - safe to call multiple times
    """
    try:
        # Get user_id from token (set by require_auth decorator)
        user_id = request.user_id

        if not user_id:
            return jsonify({"error": "Authentication failed: user_id not found"}), 401

        data = request.get_json()

        firebase_service = current_app.firebase_service

        if not firebase_service.db:
            return jsonify({"error": "Firebase not configured"}), 500

        user_ref = firebase_service.db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if user_doc.exists:
            # User already exists - return 200
            return jsonify({
                "message": "User already exists",
                "uid": user_id,
                "status": "existing"
            }), 200

        # User doesn't exist - create new document
        from datetime import datetime
        user_data = {
            "uid": user_id,
            "email": request.user_email,
            "display_name": data.get("display_name", ""),
            "displayName": data.get("display_name", ""),  # Duplicate for compatibility
            "timezone": data.get("timezone", "UTC"),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "preferences": {
                "timezone": data.get("timezone", "UTC"),
                "notifications_enabled": True
            }
        }

        user_ref.set(user_data)

        return jsonify({
            "message": "User created successfully",
            "uid": user_id,
            "status": "created"
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route('/profile', methods=['GET'])
@require_auth
def get_profile():
    """
    Get user profile (iOS compatible - no path parameter)
    Token-based authentication, returns UserProfile object directly
    """
    try:
        # Get user_id from token (set by require_auth decorator)
        user_id = request.user_id

        if not user_id:
            return jsonify({"error": "Authentication failed: user_id not found"}), 401

        firebase_service = current_app.firebase_service

        # Get user document from Firestore
        if not firebase_service.db:
            return jsonify({"error": "Firebase not configured"}), 500

        user_doc = firebase_service.db.collection('users').document(user_id).get()

        if not user_doc.exists:
            # Return default empty profile if user doesn't exist yet
            return jsonify({
                "display_name": None,
                "email": request.user_email,
                "birth_date": None,
                "photo_url": None,
                "bio": None
            }), 200

        user_data = user_doc.to_dict()

        # Extract profile fields (iOS UserProfile format)
        profile = {
            "display_name": user_data.get("display_name") or user_data.get("displayName"),
            "email": user_data.get("email") or request.user_email,
            "birth_date": user_data.get("birth_date") or user_data.get("birthDate"),
            "photo_url": user_data.get("photo_url") or user_data.get("photoURL"),
            "bio": user_data.get("bio")
        }

        return jsonify(profile), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route('/profile/<user_id>', methods=['GET'])
@require_auth
def get_profile_by_id(user_id):
    """
    Get user profile by ID (with path parameter - for compatibility)
    """
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

@auth_bp.route('/profile', methods=['PUT'])
@require_auth
def update_profile():
    """
    Update user profile (iOS compatible - no path parameter)
    Token-based authentication, accepts UserProfile object with snake_case fields
    """
    try:
        # Get user_id from token (set by require_auth decorator)
        user_id = request.user_id

        if not user_id:
            return jsonify({"error": "Authentication failed: user_id not found"}), 401

        data = request.get_json()

        if not data:
            return jsonify({"error": "Request body is required"}), 400

        firebase_service = current_app.firebase_service

        if not firebase_service.db:
            return jsonify({"error": "Firebase not configured"}), 500

        # Prepare updates (only update fields that are provided)
        updates = {}

        if "display_name" in data:
            updates["display_name"] = data["display_name"]
            updates["displayName"] = data["display_name"]  # Duplicate for compatibility

        if "email" in data:
            updates["email"] = data["email"]

        if "birth_date" in data:
            updates["birth_date"] = data["birth_date"]
            updates["birthDate"] = data["birth_date"]  # Duplicate for compatibility

        if "photo_url" in data:
            updates["photo_url"] = data["photo_url"]
            updates["photoURL"] = data["photo_url"]  # Duplicate for compatibility

        if "bio" in data:
            updates["bio"] = data["bio"]

        # Add updated timestamp
        from datetime import datetime
        updates["updated_at"] = datetime.utcnow().isoformat()

        # Update user document
        user_ref = firebase_service.db.collection('users').document(user_id)

        # Check if document exists
        user_doc = user_ref.get()
        if not user_doc.exists:
            # Create the document if it doesn't exist
            updates["created_at"] = datetime.utcnow().isoformat()
            updates["uid"] = user_id
            if request.user_email:
                updates["email"] = request.user_email
            user_ref.set(updates)
        else:
            # Update existing document
            user_ref.update(updates)

        return jsonify({"message": "Profile updated successfully"}), 200

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