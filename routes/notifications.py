from flask import Blueprint, request, jsonify, current_app
from services.firebase_service import FirebaseService
from services.notification_service import NotificationService
from services.scheduler_service import SchedulerService
import logging
import time
from functools import wraps

# Configure logging
logger = logging.getLogger(__name__)

# Create blueprint
notifications_bp = Blueprint('notifications', __name__)

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

# Initialize services (will be properly injected in app.py)
firebase_service = None
notification_service = None
scheduler_service = None

def init_notification_services(firebase_svc, notification_svc, scheduler_svc):
    """Initialize services for the notifications blueprint"""
    global firebase_service, notification_service, scheduler_service
    firebase_service = firebase_svc
    notification_service = notification_svc
    scheduler_service = scheduler_svc

@notifications_bp.route('/register-token', methods=['POST'])
@require_auth
def register_fcm_token():
    """Register or update a user's FCM device token"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Security: Use authenticated user ID instead of request body
        user_id = request.user_id
        fcm_token = data.get('fcm_token')
        
        if not fcm_token:
            return jsonify({'error': 'fcm_token is required'}), 400
        
        # Register the token
        success = notification_service.register_device_token(user_id, fcm_token)
        
        if success:
            logger.info(f"FCM token registered successfully for user: {user_id}")
            return jsonify({
                'success': True,
                'message': 'FCM token registered successfully'
            }), 200
        else:
            logger.error(f"Failed to register FCM token for user: {user_id}")
            return jsonify({
                'success': False,
                'error': 'Failed to register FCM token'
            }), 500
            
    except Exception as e:
        logger.error(f"Error in register_fcm_token: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@notifications_bp.route('/test-notification', methods=['POST'])
@require_auth
def send_test_notification():
    """Send a test notification to a user (for development/testing)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Security: Use authenticated user ID instead of request body
        user_id = request.user_id
        title = data.get('title', 'Test Notification')
        body = data.get('body', 'This is a test notification from Braindumpster')
        
        # Get user's tokens
        user_tokens = firebase_service.get_user_tokens(user_id)
        
        if not user_tokens:
            return jsonify({
                'success': False,
                'error': 'No FCM tokens found for user'
            }), 404
        
        # Send test notification
        results = notification_service.send_bulk_notifications(
            user_tokens=user_tokens,
            title=title,
            body=body,
            data={
                'type': 'test',
                'action': 'open_app',
                'timestamp': str(int(time.time()))
            }
        )
        
        success_count = sum(1 for result in results.values() if result)
        
        logger.info(f"Test notification sent: {success_count}/{len(user_tokens)} successful")
        
        return jsonify({
            'success': True,
            'message': f'Test notification sent to {success_count}/{len(user_tokens)} devices',
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Error in send_test_notification: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@notifications_bp.route('/refresh-token', methods=['POST'])
@require_auth
def refresh_fcm_token():
    """Force refresh FCM token for production reliability"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        user_id = request.user_id
        new_token = data.get('fcm_token')

        if not new_token:
            return jsonify({'error': 'FCM token is required'}), 400

        # Force refresh - cleanup old tokens and add new one
        success = notification_service.force_refresh_fcm_token(user_id, new_token)

        return jsonify({
            'success': success,
            'message': 'FCM token force refreshed successfully' if success else 'Failed to refresh FCM token'
        })

    except Exception as e:
        logger.error(f"Error in refresh_fcm_token: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@notifications_bp.route('/cleanup-tokens', methods=['POST'])
@require_auth
def cleanup_invalid_tokens():
    """Clean up invalid FCM tokens for production reliability"""
    try:
        user_id = request.user_id

        # Cleanup invalid tokens
        success = notification_service.cleanup_invalid_fcm_tokens(user_id)

        return jsonify({
            'success': success,
            'message': 'Invalid tokens cleaned successfully' if success else 'Failed to cleanup tokens'
        })

    except Exception as e:
        logger.error(f"Error in cleanup_invalid_tokens: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@notifications_bp.route('/preferences', methods=['GET', 'PUT'])
@require_auth
def notification_preferences():
    """Get or update notification preferences for a user"""
    try:
        # Security: Use authenticated user ID instead of request parameters
        user_id = request.user_id
        
        if request.method == 'GET':
            # Get current notification preferences
            # This would be implemented in firebase_service
            preferences = firebase_service.get_user_notification_preferences(user_id)
            return jsonify({
                'success': True,
                'preferences': preferences
            }), 200
            
        elif request.method == 'PUT':
            # Update notification preferences
            data = request.get_json()
            preferences = data.get('preferences', {})
            
            success = firebase_service.update_user_notification_preferences(user_id, preferences)
            
            if success:
                return jsonify({
                    'success': True,
                    'message': 'Notification preferences updated successfully'
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to update notification preferences'
                }), 500
                
    except Exception as e:
        logger.error(f"Error in notification_preferences: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@notifications_bp.route('/history/<user_id>', methods=['GET'])
@require_auth
def notification_history(user_id):
    """Get notification history for a user"""
    try:
        # Security: Ensure user can only access their own notification history
        if user_id != request.user_id:
            return jsonify({
                'success': False,
                'error': 'Unauthorized: Cannot access another user\'s notification history'
            }), 403
            
        limit = request.args.get('limit', 50, type=int)
        
        firebase_service = current_app.firebase_service
        history = firebase_service.get_notification_history(user_id, limit)
        
        return jsonify({
            'success': True,
            'history': history,
            'count': len(history)
        }), 200
        
    except Exception as e:
        logger.error(f"Error in notification_history: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@notifications_bp.route('/scheduler/status', methods=['GET'])
def scheduler_status():
    """Get current scheduler status and job information"""
    try:
        status = scheduler_service.get_scheduler_status()
        
        return jsonify({
            'success': True,
            'scheduler_status': status
        }), 200
        
    except Exception as e:
        logger.error(f"Error in scheduler_status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@notifications_bp.route('/debug-tokens/<user_id>', methods=['GET'])
def debug_user_tokens(user_id):
    """Debug endpoint to check user's FCM tokens"""
    try:
        firebase_service = current_app.firebase_service
        tokens = firebase_service.get_user_tokens(user_id)

        return jsonify({
            'success': True,
            'user_id': user_id,
            'token_count': len(tokens),
            'tokens': [f"{token[:20]}..." for token in tokens] if tokens else []
        }), 200

    except Exception as e:
        logger.error(f"Error in debug_user_tokens: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@notifications_bp.route('/force-register-token', methods=['POST'])
@require_auth
def force_register_fcm_token():
    """Force register FCM token for debugging"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        user_id = request.user_id
        fcm_token = data.get('fcm_token')

        if not fcm_token:
            return jsonify({'error': 'fcm_token is required'}), 400

        logger.info(f"🔧 FORCE registering FCM token for user: {user_id}")
        logger.info(f"🔑 Token preview: {fcm_token[:50]}...")

        # Force register the token with detailed logging
        success = notification_service.register_device_token(user_id, fcm_token)

        # Verify it was saved
        saved_tokens = current_app.firebase_service.get_user_tokens(user_id)

        return jsonify({
            'success': success,
            'message': f'Force registration {"successful" if success else "failed"}',
            'user_id': user_id,
            'token_preview': f"{fcm_token[:50]}...",
            'verification': {
                'tokens_after_save': len(saved_tokens),
                'tokens_preview': [f"{token[:20]}..." for token in saved_tokens]
            }
        }), 200 if success else 500

    except Exception as e:
        logger.error(f"Error in force_register_fcm_token: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@notifications_bp.route('/health', methods=['GET'])
def notification_health():
    """Check notification system health"""
    try:
        # Check Firebase connectivity
        db_healthy = firebase_service.health_check()
        
        # Check scheduler status
        scheduler_healthy = scheduler_service.get_scheduler_status()['status'] == 'running'
        
        # Check if we can access Firebase Messaging
        fcm_healthy = True
        try:
            from firebase_admin import messaging
            # Just importing is enough to check if FCM is available
        except Exception:
            fcm_healthy = False
        
        overall_healthy = db_healthy and scheduler_healthy and fcm_healthy
        
        return jsonify({
            'success': True,
            'healthy': overall_healthy,
            'components': {
                'database': db_healthy,
                'scheduler': scheduler_healthy,
                'fcm': fcm_healthy
            }
        }), 200 if overall_healthy else 503
        
    except Exception as e:
        logger.error(f"Error in notification_health: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500