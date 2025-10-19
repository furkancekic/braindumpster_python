import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
from firebase_admin import messaging
from firebase_admin.exceptions import FirebaseError
from models.task import Task, TaskStatus, Reminder
from services.firebase_service import FirebaseService
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotificationService:
    """Service for managing push notifications via Firebase Cloud Messaging (FCM)"""
    
    def __init__(self, firebase_service: FirebaseService):
        self.firebase_service = firebase_service
        self.config = Config()
        
    def send_push_notification(
        self, 
        user_token: str, 
        title: str, 
        body: str, 
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send a push notification to a specific user device
        
        Args:
            user_token: FCM device token
            title: Notification title
            body: Notification body
            data: Additional data payload
            
        Returns:
            bool: True if notification sent successfully, False otherwise
        """
        try:
            # Convert data values to strings (FCM requirement)
            string_data = {}
            if data:
                for key, value in data.items():
                    if isinstance(value, (dict, list)):
                        string_data[key] = json.dumps(value)
                    else:
                        string_data[key] = str(value)
            
            # Create FCM message
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=string_data,
                token=user_token,
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        icon='ic_notification',
                        color='#2196F3',
                        sound='default',
                        channel_id='voice_planner_tasks'
                    )
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            alert=messaging.ApsAlert(
                                title=title,
                                body=body
                            ),
                            badge=1,
                            sound='default'
                        )
                    )
                )
            )
            
            # Send message
            response = messaging.send(message)
            logger.info(f"Push notification sent successfully: {response}")
            return True
            
        except FirebaseError as e:
            error_msg = str(e)
            logger.error(f"Firebase error sending push notification: {error_msg}")

            # More comprehensive invalid token detection
            invalid_token_indicators = [
                "registration token is not a valid FCM registration token",
                "Requested entity was not found",
                "The registration token is not a valid FCM registration token",
                "registration-token-not-registered",
                "invalid-registration-token",
                "mismatched-credential",
                "invalid-apns-credentials"
            ]

            if any(indicator in error_msg.lower() for indicator in invalid_token_indicators):
                logger.info(f"Invalid FCM token detected, will be cleaned up: {user_token[:20]}...")
                return "INVALID_TOKEN"  # Special return value to trigger cleanup

            # Log additional details for debugging
            logger.error(f"FCM Error Details - Token: {user_token[:20]}..., Title: {title}, Body: {body[:50]}...")

            return False
        except Exception as e:
            logger.error(f"Unexpected error sending push notification: {e}")
            return False
    
    def send_bulk_notifications(
        self, 
        user_tokens: List[str], 
        title: str, 
        body: str, 
        data: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, bool]:
        """
        Send notifications to multiple device tokens
        
        Args:
            user_tokens: List of FCM device tokens
            title: Notification title
            body: Notification body
            data: Additional data payload
            user_id: User ID for token cleanup (optional)
            
        Returns:
            Dict[str, bool]: Results for each token
        """
        results = {}
        invalid_tokens = []
        
        for token in user_tokens:
            result = self.send_push_notification(token, title, body, data)
            
            if result == "INVALID_TOKEN":
                invalid_tokens.append(token)
                results[token] = False
            else:
                results[token] = result
        
        # Clean up invalid tokens if we have a user_id
        if invalid_tokens and user_id:
            logger.info(f"Cleaning up {len(invalid_tokens)} invalid tokens for user {user_id}")
            self.cleanup_invalid_tokens(user_id, invalid_tokens)
            
        return results
    
    def register_device_token(self, user_id: str, fcm_token: str) -> bool:
        """
        Register or update a user's FCM device token

        Args:
            user_id: User ID
            fcm_token: Firebase Cloud Messaging token

        Returns:
            bool: True if token registered successfully
        """
        try:
            logger.info(f"📱 Registering FCM token for user: {user_id}")
            logger.debug(f"🔑 Token preview: {fcm_token[:50]}...")

            # Store token in database
            user_tokens = self.firebase_service.get_user_tokens(user_id)
            logger.info(f"📋 Current tokens for user: {len(user_tokens)}")

            if fcm_token not in user_tokens:
                user_tokens.append(fcm_token)
                logger.info(f"➕ Added new token, total tokens: {len(user_tokens)}")
            else:
                logger.info("🔄 Token already exists, no changes needed")

            success = self.firebase_service.update_user_tokens(user_id, user_tokens)

            if success:
                logger.info(f"✅ FCM token registered successfully for user {user_id}")
                # Verify the token was saved
                saved_tokens = self.firebase_service.get_user_tokens(user_id)
                logger.info(f"🔍 Verification: User now has {len(saved_tokens)} tokens")
                return True
            else:
                logger.error(f"❌ Failed to register FCM token for user {user_id}")
                return False

        except Exception as e:
            logger.error(f"💥 Error registering device token: {e}")
            return False
    
    def send_reminder_notification(self, reminder: Reminder, task: Task) -> bool:
        """
        Send a reminder notification for a specific task
        
        Args:
            reminder: Reminder object
            task: Task object
            
        Returns:
            bool: True if notification sent successfully
        """
        try:
            # Get user's device tokens
            user_tokens = self.firebase_service.get_user_tokens(task.user_id)
            
            if not user_tokens:
                logger.warning(f"No FCM tokens found for user {task.user_id}")
                return False
            
            # Create notification content
            title = "📋 Task Reminder"
            body = f"{task.title}"
            
            # Add reminder-specific message if available
            if reminder.message and reminder.message.strip():
                body = f"{reminder.message}: {task.title}"
            
            # Create data payload
            data = {
                'type': 'reminder',
                'task_id': task.id,
                'reminder_id': reminder.id,
                'task_title': task.title,
                'task_description': task.description or '',
                'task_priority': task.priority,
                'reminder_time': reminder.reminder_time.isoformat(),
                'action': 'open_task'
            }
            
            # Send to all user devices
            results = self.send_bulk_notifications(user_tokens, title, body, data, task.user_id)
            
            # Check if at least one notification was sent successfully
            success = any(results.values())
            
            if success:
                logger.info(f"Reminder notification sent for task {task.id}")
            else:
                logger.error(f"Failed to send reminder notification for task {task.id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error sending reminder notification: {e}")
            return False
    
    def _log_notification_history(self, user_id: str, title: str, body: str, 
                                  data: Optional[Dict[str, Any]], success: bool, 
                                  response_or_error: str) -> None:
        """
        Log notification history to Firebase
        
        Args:
            user_id: User ID
            title: Notification title
            body: Notification body
            data: Additional data payload
            success: Whether notification was sent successfully
            response_or_error: FCM response or error message
        """
        try:
            from datetime import datetime
            
            history_entry = {
                'user_id': user_id,
                'title': title,
                'body': body,
                'data': data or {},
                'success': success,
                'response_or_error': response_or_error,
                'timestamp': datetime.utcnow().isoformat(),
                'notification_type': data.get('type', 'general') if data else 'general'
            }
            
            # Save to Firebase
            if hasattr(self.firebase_service, 'db') and self.firebase_service.db:
                self.firebase_service.db.collection('notification_history').add(history_entry)
                logger.debug(f"Notification history logged for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to log notification history: {e}")
    
    def send_task_approval_notification(self, task: Task) -> bool:
        """
        Send notification when a task is approved and reminders are activated
        
        Args:
            task: Approved task object
            
        Returns:
            bool: True if notification sent successfully
        """
        try:
            # Get user's device tokens
            user_tokens = self.firebase_service.get_user_tokens(task.user_id)
            
            if not user_tokens:
                logger.warning(f"No FCM tokens found for user {task.user_id}")
                return False
            
            # Create notification content
            title = "✅ Task Approved"
            body = f"'{task.title}' has been approved and reminders are now active!"
            
            # Count active reminders
            active_reminders = len([r for r in task.reminders if not r.sent])
            if active_reminders > 0:
                body += f" ({active_reminders} reminders scheduled)"
            
            # Create data payload
            data = {
                'type': 'task_approved',
                'task_id': task.id,
                'task_title': task.title,
                'task_description': task.description or '',
                'task_priority': task.priority,
                'reminder_count': str(active_reminders),
                'action': 'open_task'
            }
            
            # Send to all user devices
            results = self.send_bulk_notifications(user_tokens, title, body, data, task.user_id)
            
            # Check if at least one notification was sent successfully
            success = any(results.values())
            
            if success:
                logger.info(f"Task approval notification sent for task {task.id}")
            else:
                logger.error(f"Failed to send task approval notification for task {task.id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error sending task approval notification: {e}")
            return False
    
    def send_task_completion_notification(self, task: Task) -> bool:
        """
        Send notification when a task is completed
        
        Args:
            task: Completed task object
            
        Returns:
            bool: True if notification sent successfully
        """
        try:
            # Get user's device tokens
            user_tokens = self.firebase_service.get_user_tokens(task.user_id)
            
            if not user_tokens:
                logger.warning(f"No FCM tokens found for user {task.user_id}")
                return False
            
            # Create notification content
            title = "🎉 Task Completed"
            body = f"Great job! You've completed '{task.title}'"
            
            # Create data payload
            data = {
                'type': 'task_completed',
                'task_id': task.id,
                'task_title': task.title,
                'task_description': task.description or '',
                'action': 'open_dashboard'
            }
            
            # Send to all user devices
            results = self.send_bulk_notifications(user_tokens, title, body, data, task.user_id)
            
            # Check if at least one notification was sent successfully
            success = any(results.values())
            
            if success:
                logger.info(f"Task completion notification sent for task {task.id}")
            else:
                logger.error(f"Failed to send task completion notification for task {task.id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error sending task completion notification: {e}")
            return False
    
    def send_daily_summary_notification(self, user_id: str, summary_data: Dict[str, Any]) -> bool:
        """
        Send daily summary notification to user
        
        Args:
            user_id: User ID
            summary_data: Summary data including task counts, etc.
            
        Returns:
            bool: True if notification sent successfully
        """
        try:
            # Get user's device tokens
            user_tokens = self.firebase_service.get_user_tokens(user_id)
            
            if not user_tokens:
                logger.warning(f"No FCM tokens found for user {user_id}")
                return False
            
            # Create notification content
            pending_tasks = summary_data.get('pending_tasks', 0)
            completed_tasks = summary_data.get('completed_tasks', 0)
            
            title = "📊 Daily Summary"
            body = f"You have {pending_tasks} pending tasks and completed {completed_tasks} tasks today"
            
            # Create data payload
            data = {
                'type': 'daily_summary',
                'user_id': user_id,
                'pending_tasks': str(pending_tasks),
                'completed_tasks': str(completed_tasks),
                'action': 'open_dashboard'
            }
            
            # Send to all user devices
            results = self.send_bulk_notifications(user_tokens, title, body, data, user_id)
            
            # Check if at least one notification was sent successfully
            success = any(results.values())
            
            if success:
                logger.info(f"Daily summary notification sent for user {user_id}")
            else:
                logger.error(f"Failed to send daily summary notification for user {user_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error sending daily summary notification: {e}")
            return False
    
    def cleanup_invalid_tokens(self, user_id: str, invalid_tokens: List[str]) -> bool:
        """
        Remove invalid FCM tokens for a user
        
        Args:
            user_id: User ID
            invalid_tokens: List of invalid tokens to remove
            
        Returns:
            bool: True if cleanup successful
        """
        try:
            user_tokens = self.firebase_service.get_user_tokens(user_id)
            
            # Remove invalid tokens
            updated_tokens = [token for token in user_tokens if token not in invalid_tokens]
            
            success = self.firebase_service.update_user_tokens(user_id, updated_tokens)
            
            if success:
                logger.info(f"Cleaned up {len(invalid_tokens)} invalid tokens for user {user_id}")
                return True
            else:
                logger.error(f"Failed to cleanup invalid tokens for user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error cleaning up invalid tokens: {e}")
            return False