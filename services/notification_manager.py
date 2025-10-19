"""
Notification Manager - Central service that orchestrates all notification functionality
Integrates with existing APScheduler and manages the complete notification flow
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from .fcm_service import fcm_service
from .reminder_scheduler import reminder_scheduler
import sqlite3
import os

logger = logging.getLogger(__name__)

class NotificationManager:
    """
    Central service for managing all notification functionality
    Coordinates between FCM service, reminder scheduler, and user preferences
    """
    
    def __init__(self):
        self.db_path = os.getenv('NOTIFICATION_DB_PATH', 'notifications.db')
        self._init_database()
    
    def _init_database(self):
        """Initialize database for user notification preferences and FCM tokens"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # User FCM tokens table
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_fcm_tokens (
                        user_id TEXT PRIMARY KEY,
                        fcm_token TEXT NOT NULL,
                        platform TEXT,
                        updated_at TEXT NOT NULL,
                        is_valid BOOLEAN DEFAULT 1
                    )
                ''')
                
                # User notification settings table  
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_notification_settings (
                        user_id TEXT PRIMARY KEY,
                        notifications_enabled BOOLEAN DEFAULT 1,
                        task_reminders_enabled BOOLEAN DEFAULT 1,
                        daily_summary_enabled BOOLEAN DEFAULT 1,
                        quiet_hours_start INTEGER DEFAULT 22,
                        quiet_hours_end INTEGER DEFAULT 8,
                        updated_at TEXT NOT NULL
                    )
                ''')
                
                # Notification history for analytics
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS notification_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        notification_type TEXT NOT NULL,
                        task_id TEXT,
                        title TEXT,
                        body TEXT,
                        sent_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        fcm_response TEXT
                    )
                ''')
                
                logger.info("✅ Notification manager database initialized")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize notification database: {e}")
            raise
    
    def connect_to_scheduler(self, scheduler):
        """Connect to existing APScheduler instance"""
        try:
            reminder_scheduler.set_scheduler(scheduler)
            logger.info("✅ Notification manager connected to APScheduler")
        except Exception as e:
            logger.error(f"❌ Failed to connect to scheduler: {e}")
            raise
    
    def update_user_fcm_token(self, user_id: str, fcm_token: str, platform: str = None) -> bool:
        """Update user's FCM token"""
        try:
            # Validate token first
            is_valid = fcm_service.validate_fcm_token(fcm_token)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO user_fcm_tokens 
                    (user_id, fcm_token, platform, updated_at, is_valid)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, fcm_token, platform, datetime.now().isoformat(), is_valid))
            
            logger.info(f"✅ Updated FCM token for user {user_id}: valid={is_valid}")
            return is_valid
            
        except Exception as e:
            logger.error(f"❌ Failed to update FCM token: {e}")
            return False

    def cleanup_invalid_tokens(self, user_id: str) -> bool:
        """Clean up invalid FCM tokens for production reliability"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Remove tokens that are marked as invalid
                result = conn.execute('''
                    DELETE FROM user_fcm_tokens
                    WHERE user_id = ? AND is_valid = 0
                ''', (user_id,))

                # Also remove tokens older than 30 days
                cutoff_date = (datetime.now() - timedelta(days=30)).isoformat()
                result2 = conn.execute('''
                    DELETE FROM user_fcm_tokens
                    WHERE user_id = ? AND updated_at < ?
                ''', (user_id, cutoff_date))

                total_cleaned = result.rowcount + result2.rowcount
                logger.info(f"🧹 Cleaned {total_cleaned} invalid/old FCM tokens for user {user_id}")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to cleanup FCM tokens: {e}")
            return False
    
    def update_user_notification_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """Update user's notification preferences"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO user_notification_settings 
                    (user_id, notifications_enabled, task_reminders_enabled, daily_summary_enabled,
                     quiet_hours_start, quiet_hours_end, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    settings.get('notifications_enabled', True),
                    settings.get('task_reminders_enabled', True),
                    settings.get('daily_summary_enabled', True),
                    settings.get('quiet_hours_start', 22),
                    settings.get('quiet_hours_end', 8),
                    datetime.now().isoformat()
                ))
            
            logger.info(f"✅ Updated notification settings for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update notification settings: {e}")
            return False
    
    def get_user_fcm_token(self, user_id: str) -> Optional[str]:
        """Get user's current FCM token"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT fcm_token FROM user_fcm_tokens 
                    WHERE user_id = ? AND is_valid = 1
                ''', (user_id,))
                
                result = cursor.fetchone()
                return result[0] if result else None
                
        except Exception as e:
            logger.error(f"❌ Failed to get FCM token: {e}")
            return None
    
    def get_user_notification_settings(self, user_id: str) -> Dict[str, Any]:
        """Get user's notification preferences"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT * FROM user_notification_settings WHERE user_id = ?
                ''', (user_id,))
                
                result = cursor.fetchone()
                if not result:
                    # Return default settings
                    return {
                        'notifications_enabled': True,
                        'task_reminders_enabled': True,
                        'daily_summary_enabled': True,
                        'quiet_hours_start': 22,
                        'quiet_hours_end': 8
                    }
                
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, result))
                
        except Exception as e:
            logger.error(f"❌ Failed to get notification settings: {e}")
            return {}
    
    def on_task_approved(self, task_data: Dict[str, Any]) -> bool:
        """
        Called when a task is approved - schedules all reminders
        This is the main integration point with your existing approval endpoint
        """
        try:
            user_id = task_data.get('user_id')
            task_id = task_data.get('id')
            task_title = task_data.get('title', 'Unknown Task')
            
            logger.info(f"🎯 Task approved, scheduling reminders: {task_title} ({task_id})")
            
            # Get user's FCM token
            fcm_token = self.get_user_fcm_token(user_id)
            if not fcm_token:
                logger.warning(f"⚠️ No valid FCM token for user {user_id}, skipping reminders")
                return False
            
            # Get user's notification settings
            settings = self.get_user_notification_settings(user_id)
            
            # Check if user wants task reminders
            if not settings.get('task_reminders_enabled', True):
                logger.info(f"📵 Task reminders disabled for user {user_id}")
                return False
            
            # Schedule reminders
            job_ids = reminder_scheduler.schedule_task_reminders(
                task_data=task_data,
                user_fcm_token=fcm_token,
                user_notification_settings=settings
            )
            
            success = len(job_ids) > 0
            
            if success:
                logger.info(f"✅ Successfully scheduled {len(job_ids)} reminders for task {task_id}")
            else:
                logger.warning(f"⚠️ No reminders scheduled for task {task_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Failed to handle task approval: {e}")
            return False
    
    def on_task_updated(self, task_data: Dict[str, Any]) -> bool:
        """Called when a task is updated - reschedules reminders if needed"""
        try:
            user_id = task_data.get('user_id')
            task_id = task_data.get('id')
            
            # Get user's FCM token and settings
            fcm_token = self.get_user_fcm_token(user_id)
            if not fcm_token:
                return False
                
            settings = self.get_user_notification_settings(user_id)
            
            # Reschedule reminders
            job_ids = reminder_scheduler.reschedule_task_reminders(
                task_data=task_data,
                user_fcm_token=fcm_token,
                user_notification_settings=settings
            )
            
            logger.info(f"🔄 Rescheduled {len(job_ids)} reminders for updated task {task_id}")
            return len(job_ids) > 0
            
        except Exception as e:
            logger.error(f"❌ Failed to handle task update: {e}")
            return False
    
    def on_task_completed(self, task_id: str, user_id: str) -> bool:
        """Called when a task is completed - cancels remaining reminders"""
        try:
            cancelled_count = reminder_scheduler.cancel_task_reminders(task_id, user_id)
            logger.info(f"✅ Task completed, cancelled {cancelled_count} reminders for task {task_id}")
            return cancelled_count > 0
            
        except Exception as e:
            logger.error(f"❌ Failed to handle task completion: {e}")
            return False
    
    def on_task_deleted(self, task_id: str, user_id: str) -> bool:
        """Called when a task is deleted - cancels all reminders"""
        try:
            cancelled_count = reminder_scheduler.cancel_task_reminders(task_id, user_id)
            logger.info(f"🗑️ Task deleted, cancelled {cancelled_count} reminders for task {task_id}")
            return cancelled_count > 0
            
        except Exception as e:
            logger.error(f"❌ Failed to handle task deletion: {e}")
            return False
    
    def send_daily_summary(self, user_id: str, summary_data: Dict[str, Any]) -> bool:
        """Send daily task summary to user"""
        try:
            # Check if user wants daily summaries
            settings = self.get_user_notification_settings(user_id)
            if not settings.get('daily_summary_enabled', True):
                return False
            
            # Get FCM token
            fcm_token = self.get_user_fcm_token(user_id)
            if not fcm_token:
                return False
            
            # Send summary
            response = fcm_service.send_daily_summary(fcm_token, summary_data)
            
            # Log to history
            self._log_notification_history(
                user_id=user_id,
                notification_type='daily_summary',
                title='Daily Summary',
                body=f"Tasks: {summary_data.get('pending_tasks', 0)} pending",
                status='sent' if response else 'failed',
                fcm_response=response
            )
            
            return response is not None
            
        except Exception as e:
            logger.error(f"❌ Failed to send daily summary: {e}")
            return False
    
    def send_test_notification(self, user_id: str) -> bool:
        """Send a test notification to verify setup"""
        try:
            fcm_token = self.get_user_fcm_token(user_id)
            if not fcm_token:
                return False
            
            test_data = {
                'id': 'test',
                'title': 'Test Notification',
                'due_date': datetime.now().isoformat(),
                'priority': 'medium'
            }
            
            response = fcm_service.send_task_reminder(
                fcm_token=fcm_token,
                task_data=test_data,
                reminder_type="test"
            )
            
            return response is not None
            
        except Exception as e:
            logger.error(f"❌ Failed to send test notification: {e}")
            return False
    
    def get_notification_stats(self, user_id: str = None, days: int = 7) -> Dict[str, Any]:
        """Get notification statistics"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with sqlite3.connect(self.db_path) as conn:
                if user_id:
                    cursor = conn.execute('''
                        SELECT notification_type, status, COUNT(*) as count
                        FROM notification_history 
                        WHERE user_id = ? AND sent_at > ?
                        GROUP BY notification_type, status
                    ''', (user_id, cutoff_date.isoformat()))
                else:
                    cursor = conn.execute('''
                        SELECT notification_type, status, COUNT(*) as count
                        FROM notification_history 
                        WHERE sent_at > ?
                        GROUP BY notification_type, status
                    ''', (cutoff_date.isoformat(),))
                
                results = cursor.fetchall()
                
                stats = {
                    'total_sent': 0,
                    'total_failed': 0,
                    'by_type': {}
                }
                
                for notif_type, status, count in results:
                    if notif_type not in stats['by_type']:
                        stats['by_type'][notif_type] = {'sent': 0, 'failed': 0}
                    
                    stats['by_type'][notif_type][status] = count
                    
                    if status == 'sent':
                        stats['total_sent'] += count
                    elif status == 'failed':
                        stats['total_failed'] += count
                
                return stats
                
        except Exception as e:
            logger.error(f"❌ Failed to get notification stats: {e}")
            return {}
    
    def _log_notification_history(
        self,
        user_id: str,
        notification_type: str,
        title: str,
        body: str,
        status: str,
        task_id: str = None,
        fcm_response: str = None
    ):
        """Log notification to history for analytics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO notification_history 
                    (user_id, notification_type, task_id, title, body, sent_at, status, fcm_response)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    notification_type,
                    task_id,
                    title,
                    body,
                    datetime.now().isoformat(),
                    status,
                    str(fcm_response) if fcm_response else None
                ))
                
        except Exception as e:
            logger.error(f"Failed to log notification history: {e}")
    
    def cleanup(self):
        """Cleanup old data and invalid tokens"""
        try:
            # Cleanup old reminders
            reminder_scheduler.cleanup_old_reminders(days=30)
            
            # Cleanup old notification history
            cutoff_date = datetime.now() - timedelta(days=90)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    DELETE FROM notification_history 
                    WHERE sent_at < ?
                ''', (cutoff_date.isoformat(),))
                
                deleted_count = cursor.rowcount
                
            logger.info(f"🧹 Cleaned up {deleted_count} old notification records")
            
        except Exception as e:
            logger.error(f"❌ Failed to cleanup: {e}")

# Global notification manager instance
notification_manager = NotificationManager()