from flask import Blueprint, request, jsonify, current_app
from functools import wraps

users_bp = Blueprint('users', __name__)

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

@users_bp.route('/me', methods=['DELETE'])
@require_auth
def delete_account():
    """
    Delete user account (iOS compatible)
    Deletes user data from Firestore and Firebase Authentication
    """
    try:
        # Get user_id from token (set by require_auth decorator)
        user_id = request.user_id

        if not user_id:
            return jsonify({"error": "Authentication failed: user_id not found"}), 401

        firebase_service = current_app.firebase_service

        if not firebase_service.db:
            return jsonify({"error": "Firebase not configured"}), 500

        # Delete user tasks
        tasks_ref = firebase_service.db.collection('tasks').where('user_id', '==', user_id)
        tasks = tasks_ref.stream()

        task_count = 0
        for task in tasks:
            task.reference.delete()
            task_count += 1

        # Delete user conversations
        conversations_ref = firebase_service.db.collection('conversations').where('user_id', '==', user_id)
        conversations = conversations_ref.stream()

        conversation_count = 0
        for conversation in conversations:
            conversation.reference.delete()
            conversation_count += 1

        # Delete user subscriptions
        subscriptions_ref = firebase_service.db.collection('subscriptions').where('user_id', '==', user_id)
        subscriptions = subscriptions_ref.stream()

        subscription_count = 0
        for subscription in subscriptions:
            subscription.reference.delete()
            subscription_count += 1

        # Delete user document
        firebase_service.db.collection('users').document(user_id).delete()

        # Delete from Firebase Authentication
        try:
            import firebase_admin
            from firebase_admin import auth as firebase_auth
            firebase_auth.delete_user(user_id)
        except Exception as auth_error:
            # Log error but don't fail the request
            # User data is already deleted from Firestore
            print(f"⚠️ Failed to delete from Firebase Auth: {auth_error}")

        return jsonify({
            "message": "Account deleted successfully",
            "deleted": {
                "tasks": task_count,
                "conversations": conversation_count,
                "subscriptions": subscription_count,
                "user": True
            }
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
