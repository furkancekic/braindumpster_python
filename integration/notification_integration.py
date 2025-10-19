"""
Integration layer to connect the new enhanced notification system 
with the existing APScheduler and Flask application
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from ..services.notification_manager import notification_manager
from ..services.fcm_service import fcm_service

logger = logging.getLogger(__name__)

class NotificationIntegration:
    """
    Integration class that connects the enhanced notification system
    with the existing Flask app and APScheduler
    """
    
    def __init__(self):
        self.is_initialized = False
        self.app = None
        self.scheduler = None
    
    def initialize(self, app, scheduler_service=None):
        """
        Initialize the notification integration with Flask app and scheduler
        
        Args:
            app: Flask application instance
            scheduler_service: Existing scheduler service with APScheduler
        """
        try:
            self.app = app
            
            # Get the APScheduler from the existing scheduler service
            if scheduler_service and hasattr(scheduler_service, 'scheduler'):
                self.scheduler = scheduler_service.scheduler
                logger.info("✅ Connected to existing APScheduler")
            else:
                logger.warning("⚠️ No scheduler service provided, creating standalone scheduler")
            
            # Connect notification manager to the scheduler
            notification_manager.connect_to_scheduler(self.scheduler)
            
            # Initialize FCM service with Firebase credentials
            firebase_creds_path = app.config.get('FIREBASE_SERVICE_ACCOUNT_PATH')
            if firebase_creds_path:
                fcm_service.initialize(firebase_creds_path)
                logger.info("✅ FCM service initialized with app config")
            else:
                logger.warning("⚠️ No Firebase service account path in config")
            
            self.is_initialized = True
            logger.info("🚀 Enhanced notification system integration completed")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize notification integration: {e}")
            raise
    
    def on_task_approved(self, task_data: Dict[str, Any]) -> bool:
        """
        Hook for when tasks are approved - schedules notifications
        
        This method should be called from the existing approval endpoint
        to automatically schedule push notifications for task reminders
        
        Args:
            task_data: Task information from Firebase/database
            
        Returns:
            bool: True if notifications were scheduled successfully
        """
        try:
            if not self.is_initialized:
                logger.warning("⚠️ Notification integration not initialized")
                return False
                
            logger.info(f"🎯 Task approved, processing for notifications: {task_data.get('title')}")
            
            # Let the notification manager handle the rest
            return notification_manager.on_task_approved(task_data)
            
        except Exception as e:
            logger.error(f"❌ Error in task approval hook: {e}")
            return False
    
    def on_task_updated(self, task_data: Dict[str, Any]) -> bool:
        """Hook for when tasks are updated"""
        try:
            if not self.is_initialized:
                return False
                
            return notification_manager.on_task_updated(task_data)
            
        except Exception as e:
            logger.error(f"❌ Error in task update hook: {e}")
            return False
    
    def on_task_completed(self, task_id: str, user_id: str) -> bool:
        """Hook for when tasks are completed"""
        try:
            if not self.is_initialized:
                return False
                
            return notification_manager.on_task_completed(task_id, user_id)
            
        except Exception as e:
            logger.error(f"❌ Error in task completion hook: {e}")
            return False
    
    def on_task_deleted(self, task_id: str, user_id: str) -> bool:
        """Hook for when tasks are deleted - cancels all scheduled reminders"""
        try:
            if not self.is_initialized:
                return False
                
            logger.info(f"🗑️ Task deleted, cancelling all reminders: {task_id}")
            return notification_manager.on_task_deleted(task_id, user_id)
            
        except Exception as e:
            logger.error(f"❌ Error in task deletion hook: {e}")
            return False
    
    def on_reminders_updated(self, task_data: Dict[str, Any], removed_reminder_ids: list = None) -> bool:
        """
        Hook for when task reminders are updated or specific reminders are deleted
        
        Args:
            task_data: Updated task information
            removed_reminder_ids: List of reminder IDs that were removed (optional)
        """
        try:
            if not self.is_initialized:
                return False
                
            task_id = task_data.get('id')
            user_id = task_data.get('user_id')
            
            logger.info(f"⏰ Task reminders updated, rescheduling: {task_id}")
            
            # If specific reminders were removed, we could cancel only those
            # For now, we'll reschedule all reminders (simpler and more reliable)
            return notification_manager.on_task_updated(task_data)
            
        except Exception as e:
            logger.error(f"❌ Error in reminders update hook: {e}")
            return False
    
    def update_user_fcm_token(self, user_id: str, fcm_token: str, platform: str = None) -> bool:
        """Update user's FCM token"""
        try:
            if not self.is_initialized:
                return False
                
            return notification_manager.update_user_fcm_token(user_id, fcm_token, platform)

        except Exception as e:
            logger.error(f"❌ Error updating FCM token: {e}")
            return False

    def cleanup_invalid_fcm_tokens(self, user_id: str) -> bool:
        """Clean up invalid FCM tokens for production reliability"""
        try:
            if not self.is_initialized:
                return False

            logger.info(f"🧹 Cleaning up invalid FCM tokens for user: {user_id}")
            return notification_manager.cleanup_invalid_tokens(user_id)

        except Exception as e:
            logger.error(f"❌ Error cleaning FCM tokens: {e}")
            return False

    def force_refresh_fcm_token(self, user_id: str, new_token: str) -> bool:
        """Force refresh FCM token (replace all existing tokens)"""
        try:
            if not self.is_initialized:
                return False

            logger.info(f"🔄 Force refreshing FCM token for user: {user_id}")
            # First cleanup old tokens
            notification_manager.cleanup_invalid_tokens(user_id)
            # Then add new token
            return notification_manager.update_user_fcm_token(user_id, new_token, 'mobile')

        except Exception as e:
            logger.error(f"❌ Error force refreshing FCM token: {e}")
            return False
    
    def update_user_notification_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """Update user's notification preferences"""
        try:
            if not self.is_initialized:
                return False
                
            return notification_manager.update_user_notification_settings(user_id, settings)
            
        except Exception as e:
            logger.error(f"❌ Error updating notification settings: {e}")
            return False
    
    def send_test_notification(self, user_id: str) -> bool:
        """Send a test notification to user"""
        try:
            if not self.is_initialized:
                return False
                
            return notification_manager.send_test_notification(user_id)
            
        except Exception as e:
            logger.error(f"❌ Error sending test notification: {e}")
            return False
    
    def get_notification_stats(self, user_id: str = None) -> Dict[str, Any]:
        """Get notification statistics"""
        try:
            if not self.is_initialized:
                return {}
                
            return notification_manager.get_notification_stats(user_id)
            
        except Exception as e:
            logger.error(f"❌ Error getting notification stats: {e}")
            return {}

# Global instance
notification_integration = NotificationIntegration()

def integrate_with_existing_scheduler(scheduler_service):
    """
    Helper function to integrate with the existing scheduler service
    This should be called from your existing SchedulerService class
    """
    try:
        # Patch the existing scheduler service to use our enhanced notifications
        original_schedule_reminder = getattr(scheduler_service, 'schedule_reminder_for_task', None)
        
        def enhanced_schedule_reminder_for_task(task):
            """Enhanced version that uses the new notification system"""
            try:
                # Convert task object to dict format expected by notification manager
                task_data = {
                    'id': task.id,
                    'title': task.title,
                    'description': task.description,
                    'user_id': task.user_id,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'priority': task.priority.value if hasattr(task.priority, 'value') else str(task.priority),
                    'status': task.status.value if hasattr(task.status, 'value') else str(task.status),
                    'reminders': []
                }
                
                # Convert reminders to dict format
                if hasattr(task, 'reminders') and task.reminders:
                    for reminder in task.reminders:
                        reminder_data = {
                            'reminder_time': reminder.reminder_time.isoformat() if reminder.reminder_time else None,
                            'message': getattr(reminder, 'message', ''),
                            'type': getattr(reminder, 'type', 'task_reminder')
                        }
                        task_data['reminders'].append(reminder_data)
                
                logger.info(f"📬 Enhanced scheduling for task: {task.title}")
                
                # Use the enhanced notification system
                success = notification_integration.on_task_approved(task_data)
                
                # Fallback to original method if available
                if not success and original_schedule_reminder:
                    logger.info("Falling back to original scheduler")
                    return original_schedule_reminder(task)
                    
                return success
                
            except Exception as e:
                logger.error(f"❌ Error in enhanced scheduler: {e}")
                # Fallback to original method
                if original_schedule_reminder:
                    return original_schedule_reminder(task)
                return False
        
        # Replace the method
        scheduler_service.schedule_reminder_for_task = enhanced_schedule_reminder_for_task
        logger.info("✅ Enhanced notification system integrated with existing scheduler")
        
    except Exception as e:
        logger.error(f"❌ Failed to integrate with existing scheduler: {e}")

def patch_existing_endpoints(app):
    """
    Patch existing task endpoints to include notification cleanup
    This modifies the existing delete and update endpoints to handle notifications
    """
    try:
        # Import here to avoid circular imports
        from ..routes.tasks import tasks_bp
        
        # Get the original delete function
        original_delete_task = None
        for rule in app.url_map.iter_rules():
            if rule.endpoint == 'tasks.delete_task':
                original_delete_task = app.view_functions[rule.endpoint]
                break
        
        if original_delete_task:
            def enhanced_delete_task(task_id):
                """Enhanced delete task function with notification cleanup"""
                from flask import request, jsonify, current_app
                
                try:
                    # Get user_id from auth token
                    user_id = getattr(request, 'user_id', None)
                    
                    # Get task data before deletion for notification cleanup
                    firebase_service = current_app.firebase_service
                    task_data = firebase_service.get_task(task_id)
                    
                    if task_data and user_id:
                        # Cancel all scheduled reminders for this task
                        notification_integration.on_task_deleted(task_id, user_id)
                        logger.info(f"🗑️ Cancelled reminders for deleted task: {task_id}")
                    
                    # Call original delete function
                    return original_delete_task(task_id)
                    
                except Exception as e:
                    logger.error(f"❌ Error in enhanced delete task: {e}")
                    # Fallback to original function
                    return original_delete_task(task_id)
            
            # Replace the function
            app.view_functions['tasks.delete_task'] = enhanced_delete_task
            logger.info("✅ Enhanced delete_task endpoint with notification cleanup")
        
        # Patch batch delete as well
        original_batch_delete = None
        for rule in app.url_map.iter_rules():
            if rule.endpoint == 'tasks.batch_delete_tasks':
                original_batch_delete = app.view_functions[rule.endpoint]
                break
        
        if original_batch_delete:
            def enhanced_batch_delete_tasks():
                """Enhanced batch delete with notification cleanup"""
                from flask import request, jsonify, current_app
                
                try:
                    # Get request data
                    data = request.get_json()
                    task_ids = data.get('task_ids', [])
                    user_id = getattr(request, 'user_id', None)
                    
                    if task_ids and user_id:
                        # Cancel reminders for all tasks being deleted
                        for task_id in task_ids:
                            try:
                                notification_integration.on_task_deleted(task_id, user_id)
                            except Exception as e:
                                logger.warning(f"Failed to cancel reminders for task {task_id}: {e}")
                        
                        logger.info(f"🗑️ Cancelled reminders for {len(task_ids)} deleted tasks")
                    
                    # Call original batch delete function
                    return original_batch_delete()
                    
                except Exception as e:
                    logger.error(f"❌ Error in enhanced batch delete: {e}")
                    # Fallback to original function
                    return original_batch_delete()
            
            # Replace the function
            app.view_functions['tasks.batch_delete_tasks'] = enhanced_batch_delete_tasks
            logger.info("✅ Enhanced batch_delete_tasks endpoint with notification cleanup")
        
        logger.info("🔧 Successfully patched existing endpoints for notification cleanup")
        
    except Exception as e:
        logger.error(f"❌ Failed to patch existing endpoints: {e}")

def setup_notification_endpoints(app, notifications_bp):
    """
    Add new notification endpoints to the existing notifications blueprint
    """
    
    @notifications_bp.route('/fcm-token', methods=['PUT'])
    def update_fcm_token():
        """Update user's FCM token"""
        from flask import request, jsonify
        from ..utils.auth import require_auth
        
        @require_auth
        def _update_fcm_token():
            try:
                data = request.get_json()
                if not data or 'fcm_token' not in data:
                    return jsonify({'error': 'fcm_token is required'}), 400
                
                user_id = request.user_id
                fcm_token = data['fcm_token']
                platform = data.get('platform', 'unknown')
                
                success = notification_integration.update_user_fcm_token(user_id, fcm_token, platform)
                
                if success:
                    return jsonify({'message': 'FCM token updated successfully'})
                else:
                    return jsonify({'error': 'Failed to update FCM token'}), 400
                    
            except Exception as e:
                logger.error(f"Error updating FCM token: {e}")
                return jsonify({'error': str(e)}), 500
        
        return _update_fcm_token()
    
    @notifications_bp.route('/user-settings', methods=['PUT'])
    def update_notification_settings():
        """Update user's notification settings"""
        from flask import request, jsonify
        from ..utils.auth import require_auth
        
        @require_auth 
        def _update_settings():
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'Settings data is required'}), 400
                
                user_id = request.user_id
                success = notification_integration.update_user_notification_settings(user_id, data)
                
                if success:
                    return jsonify({'message': 'Notification settings updated successfully'})
                else:
                    return jsonify({'error': 'Failed to update notification settings'}), 400
                    
            except Exception as e:
                logger.error(f"Error updating notification settings: {e}")
                return jsonify({'error': str(e)}), 500
        
        return _update_settings()
    
    @notifications_bp.route('/test', methods=['POST'])
    def send_test_notification():
        """Send a test notification"""
        from flask import request, jsonify
        from ..utils.auth import require_auth
        
        @require_auth
        def _send_test():
            try:
                user_id = request.user_id
                success = notification_integration.send_test_notification(user_id)
                
                if success:
                    return jsonify({'message': 'Test notification sent successfully'})
                else:
                    return jsonify({'error': 'Failed to send test notification'}), 400
                    
            except Exception as e:
                logger.error(f"Error sending test notification: {e}")
                return jsonify({'error': str(e)}), 500
        
        return _send_test()
    
    @notifications_bp.route('/stats', methods=['GET'])
    def get_notification_stats():
        """Get notification statistics"""
        from flask import request, jsonify
        from ..utils.auth import require_auth
        
        @require_auth
        def _get_stats():
            try:
                user_id = request.user_id
                stats = notification_integration.get_notification_stats(user_id)
                return jsonify(stats)
                    
            except Exception as e:
                logger.error(f"Error getting notification stats: {e}")
                return jsonify({'error': str(e)}), 500
        
        return _get_stats()
    
    logger.info("✅ Enhanced notification endpoints added to blueprint")