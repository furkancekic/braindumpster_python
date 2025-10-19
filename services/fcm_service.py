"""
Firebase Cloud Messaging Service for sending push notifications
"""
import logging
import firebase_admin
from firebase_admin import credentials, messaging
from typing import Optional, Dict, Any, List
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class FCMService:
    """Service for sending Firebase Cloud Messaging notifications"""
    
    def __init__(self):
        self._app = None
        self._initialized = False
        
    def initialize(self, service_account_path: Optional[str] = None):
        """Initialize Firebase Admin SDK"""
        try:
            if self._initialized:
                logger.info("FCM Service already initialized")
                return
                
            # Use provided path or environment variable
            cred_path = service_account_path or os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
            
            if not cred_path:
                logger.error("No Firebase service account path provided")
                raise ValueError("Firebase service account path is required")
                
            if not os.path.exists(cred_path):
                logger.error(f"Firebase service account file not found: {cred_path}")
                raise FileNotFoundError(f"Service account file not found: {cred_path}")
                
            # Initialize Firebase Admin SDK
            cred = credentials.Certificate(cred_path)
            self._app = firebase_admin.initialize_app(cred, name='fcm_service')
            self._initialized = True
            
            logger.info("✅ FCM Service initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize FCM Service: {e}")
            raise
    
    def send_task_reminder(
        self, 
        fcm_token: str, 
        task_data: Dict[str, Any],
        reminder_type: str = "task_reminder"
    ) -> Optional[str]:
        """Send a task reminder notification to a specific device"""
        try:
            if not self._initialized:
                logger.error("FCM Service not initialized")
                return None
                
            # Extract task information
            task_id = task_data.get('id', '')
            task_title = task_data.get('title', 'Task Reminder')
            due_time = task_data.get('due_date', '')
            priority = task_data.get('priority', 'medium')
            
            # Format due time for display
            due_display = self._format_due_time(due_time)
            
            # Create notification content based on priority
            title, body = self._create_notification_content(
                task_title, due_display, priority, reminder_type
            )
            
            # Create the notification message
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data={
                    'type': reminder_type,
                    'task_id': task_id,
                    'task_title': task_title,
                    'due_time': due_time,
                    'priority': priority,
                    'timestamp': str(int(datetime.now().timestamp()))
                },
                token=fcm_token,
                # Configure notification behavior
                android=messaging.AndroidConfig(
                    notification=messaging.AndroidNotification(
                        icon='ic_notification',
                        color='#FF6B35',
                        sound='default',
                        channel_id='task_reminders'
                    ),
                    priority='high'
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound='default',
                            badge=1,
                            category='TASK_REMINDER'
                        )
                    )
                )
            )
            
            # Send the notification
            response = messaging.send(message, app=self._app)
            logger.info(f"✅ Notification sent successfully: {response}")
            logger.info(f"Task: {task_title}, User token: {fcm_token[:20]}...")
            
            return response
            
        except messaging.UnregisteredError:
            logger.warning(f"⚠️ FCM token is unregistered: {fcm_token[:20]}...")
            return None
        except messaging.SenderIdMismatchError:
            logger.error(f"❌ FCM token sender ID mismatch: {fcm_token[:20]}...")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to send notification: {e}")
            return None
    
    def send_daily_summary(
        self, 
        fcm_token: str, 
        summary_data: Dict[str, Any]
    ) -> Optional[str]:
        """Send a daily task summary notification"""
        try:
            if not self._initialized:
                logger.error("FCM Service not initialized")
                return None
                
            pending_count = summary_data.get('pending_tasks', 0)
            overdue_count = summary_data.get('overdue_tasks', 0)
            completed_count = summary_data.get('completed_today', 0)
            
            # Create summary message
            if pending_count == 0 and overdue_count == 0:
                title = "🎉 All Done!"
                body = f"Great job! You completed {completed_count} tasks today."
            else:
                title = "📋 Daily Summary"
                body = f"{pending_count} pending, {overdue_count} overdue, {completed_count} completed"
            
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data={
                    'type': 'daily_summary',
                    'pending_tasks': str(pending_count),
                    'overdue_tasks': str(overdue_count),
                    'completed_today': str(completed_count),
                    'timestamp': str(int(datetime.now().timestamp()))
                },
                token=fcm_token
            )
            
            response = messaging.send(message, app=self._app)
            logger.info(f"✅ Daily summary sent: {response}")
            return response
            
        except Exception as e:
            logger.error(f"❌ Failed to send daily summary: {e}")
            return None
    
    def send_bulk_notifications(
        self, 
        notifications: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Send notifications to multiple devices efficiently"""
        try:
            if not self._initialized:
                logger.error("FCM Service not initialized")
                return {'success': 0, 'failure': 0, 'errors': []}
                
            if not notifications:
                return {'success': 0, 'failure': 0, 'errors': []}
                
            # Prepare messages
            messages = []
            for notif in notifications:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=notif['title'],
                        body=notif['body']
                    ),
                    data=notif.get('data', {}),
                    token=notif['token']
                )
                messages.append(message)
            
            # Send batch
            response = messaging.send_all(messages, app=self._app)
            
            logger.info(f"✅ Bulk notifications sent: {response.success_count} success, {response.failure_count} failed")
            
            # Log failed tokens for cleanup
            failed_tokens = []
            for idx, result in enumerate(response.responses):
                if not result.success:
                    failed_tokens.append({
                        'token': notifications[idx]['token'][:20] + '...',
                        'error': result.exception.code if result.exception else 'Unknown'
                    })
            
            return {
                'success': response.success_count,
                'failure': response.failure_count,
                'errors': failed_tokens
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to send bulk notifications: {e}")
            return {'success': 0, 'failure': len(notifications), 'errors': [str(e)]}
    
    def validate_fcm_token(self, fcm_token: str) -> bool:
        """Validate if an FCM token is valid by sending a dry-run message"""
        try:
            if not self._initialized:
                return False
                
            # Create a test message with dry_run=True
            message = messaging.Message(
                notification=messaging.Notification(
                    title="Test",
                    body="Test"
                ),
                token=fcm_token
            )
            
            # Send dry run (doesn't actually send notification)
            messaging.send(message, dry_run=True, app=self._app)
            return True
            
        except messaging.UnregisteredError:
            logger.warning(f"FCM token unregistered: {fcm_token[:20]}...")
            return False
        except Exception as e:
            logger.warning(f"FCM token validation failed: {e}")
            return False
    
    def _format_due_time(self, due_time: str) -> str:
        """Format due time for display in notifications"""
        try:
            if not due_time:
                return ""
                
            # Parse the due time
            if isinstance(due_time, str):
                due_dt = datetime.fromisoformat(due_time.replace('Z', '+00:00'))
            else:
                due_dt = due_time
                
            now = datetime.now(due_dt.tzinfo)
            diff = due_dt - now
            
            if diff.total_seconds() < 0:
                return "overdue"
            elif diff.total_seconds() < 3600:  # Less than 1 hour
                minutes = int(diff.total_seconds() / 60)
                return f"due in {minutes} minutes"
            elif diff.total_seconds() < 86400:  # Less than 1 day
                hours = int(diff.total_seconds() / 3600)
                return f"due in {hours} hours"
            else:
                days = diff.days
                return f"due in {days} days"
                
        except Exception as e:
            logger.warning(f"Failed to format due time: {e}")
            return ""
    
    def _create_notification_content(
        self, 
        task_title: str, 
        due_display: str, 
        priority: str, 
        reminder_type: str
    ) -> tuple[str, str]:
        """Create notification title and body based on task details"""
        
        # Priority emojis
        priority_emojis = {
            'high': '🔥',
            'medium': '⚡',
            'low': '📝'
        }
        
        emoji = priority_emojis.get(priority.lower(), '📝')
        
        if reminder_type == "task_due":
            title = f"{emoji} Task Due Now!"
            body = f"{task_title}"
            if due_display and due_display != "overdue":
                body += f" - {due_display}"
        elif reminder_type == "task_overdue":
            title = f"⚠️ Overdue Task"
            body = f"{task_title} is overdue"
        else:  # task_reminder
            title = f"{emoji} Task Reminder"
            body = f"{task_title}"
            if due_display:
                body += f" - {due_display}"
        
        return title, body
    
    def cleanup(self):
        """Clean up Firebase app resources"""
        try:
            if self._app:
                firebase_admin.delete_app(self._app)
                self._app = None
                self._initialized = False
                logger.info("FCM Service cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up FCM Service: {e}")

# Global FCM service instance
fcm_service = FCMService()