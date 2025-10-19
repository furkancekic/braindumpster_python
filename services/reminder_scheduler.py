"""
Reminder Scheduler Service that works with existing APScheduler
Automatically schedules and sends push notifications for task reminders
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
import sqlite3
import json
import os
from .fcm_service import fcm_service

logger = logging.getLogger(__name__)

class ReminderScheduler:
    """Manages scheduling and sending of task reminder notifications"""
    
    def __init__(self, scheduler: Optional[BackgroundScheduler] = None):
        """
        Initialize with existing scheduler or create new one
        
        Args:
            scheduler: Existing APScheduler instance (recommended to use existing one)
        """
        self.scheduler = scheduler
        self.db_path = os.getenv('REMINDER_DB_PATH', 'reminders.db')
        self._init_database()
        
        # Initialize FCM service
        try:
            fcm_service.initialize()
        except Exception as e:
            logger.error(f"Failed to initialize FCM service: {e}")
    
    def set_scheduler(self, scheduler: BackgroundScheduler):
        """Set the APScheduler instance (use existing one from your app)"""
        self.scheduler = scheduler
        logger.info("✅ Reminder scheduler connected to existing APScheduler")
    
    def _init_database(self):
        """Initialize SQLite database for tracking scheduled reminders"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS scheduled_reminders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        fcm_token TEXT NOT NULL,
                        reminder_time TEXT NOT NULL,
                        reminder_type TEXT NOT NULL,
                        job_id TEXT UNIQUE NOT NULL,
                        task_data TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        sent_at TEXT NULL,
                        status TEXT DEFAULT 'scheduled'
                    )
                ''')
                
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_reminder_time 
                    ON scheduled_reminders(reminder_time)
                ''')
                
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_task_user 
                    ON scheduled_reminders(task_id, user_id)
                ''')
                
                logger.info("✅ Reminder database initialized")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize reminder database: {e}")
            raise
    
    def schedule_task_reminders(
        self, 
        task_data: Dict[str, Any], 
        user_fcm_token: str,
        user_notification_settings: Dict[str, Any] = None
    ) -> List[str]:
        """
        Schedule all reminders for a task when it's approved
        
        Args:
            task_data: Task information from database
            user_fcm_token: User's FCM token for notifications
            user_notification_settings: User's notification preferences
            
        Returns:
            List of scheduled job IDs
        """
        try:
            if not self.scheduler:
                logger.error("No scheduler available")
                return []
                
            # Check if notifications are enabled for user
            if not self._should_send_notifications(user_notification_settings):
                logger.info(f"Notifications disabled for user, skipping reminders")
                return []
                
            # Validate FCM token
            if not fcm_service.validate_fcm_token(user_fcm_token):
                logger.warning(f"Invalid FCM token, skipping reminders")
                return []
                
            scheduled_jobs = []
            task_id = task_data.get('id')
            user_id = task_data.get('user_id')
            reminders = task_data.get('reminders', [])
            due_date = task_data.get('due_date')
            
            logger.info(f"📅 Scheduling reminders for task: {task_data.get('title')} ({task_id})")
            logger.info(f"Found {len(reminders)} reminder times")
            
            # Schedule specific reminder times
            for reminder in reminders:
                try:
                    reminder_time = self._parse_reminder_time(reminder)
                    if not reminder_time:
                        continue
                        
                    # Skip past reminders
                    if reminder_time <= datetime.now():
                        logger.info(f"Skipping past reminder time: {reminder_time}")
                        continue
                    
                    # Check quiet hours
                    if self._is_quiet_hours(reminder_time, user_notification_settings):
                        logger.info(f"Skipping reminder during quiet hours: {reminder_time}")
                        continue
                    
                    job_id = self._schedule_single_reminder(
                        task_data=task_data,
                        user_id=user_id,
                        fcm_token=user_fcm_token,
                        reminder_time=reminder_time,
                        reminder_type="task_reminder"
                    )
                    
                    if job_id:
                        scheduled_jobs.append(job_id)
                        
                except Exception as e:
                    logger.error(f"Failed to schedule reminder: {e}")
                    continue
            
            # Schedule due date notification (if no specific reminders)
            if due_date and not reminders:
                try:
                    due_dt = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                    
                    # Schedule notification 1 hour before due time
                    reminder_time = due_dt - timedelta(hours=1)
                    if reminder_time > datetime.now():
                        job_id = self._schedule_single_reminder(
                            task_data=task_data,
                            user_id=user_id,
                            fcm_token=user_fcm_token,
                            reminder_time=reminder_time,
                            reminder_type="task_due"
                        )
                        if job_id:
                            scheduled_jobs.append(job_id)
                    
                    # Schedule overdue notification 1 hour after due time
                    overdue_time = due_dt + timedelta(hours=1)
                    job_id = self._schedule_single_reminder(
                        task_data=task_data,
                        user_id=user_id,
                        fcm_token=user_fcm_token,
                        reminder_time=overdue_time,
                        reminder_type="task_overdue"
                    )
                    if job_id:
                        scheduled_jobs.append(job_id)
                        
                except Exception as e:
                    logger.error(f"Failed to schedule due date reminders: {e}")
            
            logger.info(f"✅ Scheduled {len(scheduled_jobs)} reminders for task {task_id}")
            return scheduled_jobs
            
        except Exception as e:
            logger.error(f"❌ Failed to schedule task reminders: {e}")
            return []
    
    def _schedule_single_reminder(
        self,
        task_data: Dict[str, Any],
        user_id: str,
        fcm_token: str,
        reminder_time: datetime,
        reminder_type: str
    ) -> Optional[str]:
        """Schedule a single reminder notification"""
        try:
            task_id = task_data.get('id')
            job_id = f"reminder_{task_id}_{user_id}_{reminder_type}_{int(reminder_time.timestamp())}"
            
            # Add job to scheduler
            self.scheduler.add_job(
                func=self._send_reminder_notification,
                trigger=DateTrigger(run_date=reminder_time),
                args=[task_data, fcm_token, reminder_type, job_id],
                id=job_id,
                replace_existing=True,
                misfire_grace_time=300  # 5 minutes grace period
            )
            
            # Store in database
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO scheduled_reminders 
                    (task_id, user_id, fcm_token, reminder_time, reminder_type, job_id, task_data, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id,
                    user_id,
                    fcm_token,
                    reminder_time.isoformat(),
                    reminder_type,
                    job_id,
                    json.dumps(task_data),
                    datetime.now().isoformat()
                ))
            
            logger.info(f"📝 Scheduled {reminder_type} for {reminder_time}: {job_id}")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to schedule single reminder: {e}")
            return None
    
    def _send_reminder_notification(
        self, 
        task_data: Dict[str, Any], 
        fcm_token: str, 
        reminder_type: str,
        job_id: str
    ):
        """Callback function that gets executed by APScheduler to send notification"""
        try:
            logger.info(f"🔔 Sending {reminder_type} notification for task: {task_data.get('title')}")
            
            # Send the notification
            response = fcm_service.send_task_reminder(
                fcm_token=fcm_token,
                task_data=task_data,
                reminder_type=reminder_type
            )
            
            # Update database record
            status = 'sent' if response else 'failed'
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE scheduled_reminders 
                    SET sent_at = ?, status = ?
                    WHERE job_id = ?
                ''', (datetime.now().isoformat(), status, job_id))
            
            if response:
                logger.info(f"✅ Notification sent successfully: {job_id}")
            else:
                logger.error(f"❌ Failed to send notification: {job_id}")
                
        except Exception as e:
            logger.error(f"❌ Error in reminder callback: {e}")
            # Update as failed
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute('''
                        UPDATE scheduled_reminders 
                        SET status = 'failed'
                        WHERE job_id = ?
                    ''', (job_id,))
            except:
                pass
    
    def cancel_task_reminders(self, task_id: str, user_id: str) -> int:
        """Cancel all scheduled reminders for a task"""
        try:
            # Get all job IDs for this task
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT job_id FROM scheduled_reminders 
                    WHERE task_id = ? AND user_id = ? AND status = 'scheduled'
                ''', (task_id, user_id))
                
                job_ids = [row[0] for row in cursor.fetchall()]
            
            cancelled_count = 0
            for job_id in job_ids:
                try:
                    # Remove from scheduler
                    self.scheduler.remove_job(job_id)
                    cancelled_count += 1
                    logger.info(f"Cancelled reminder job: {job_id}")
                except Exception as e:
                    logger.warning(f"Failed to cancel job {job_id}: {e}")
            
            # Update database
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE scheduled_reminders 
                    SET status = 'cancelled'
                    WHERE task_id = ? AND user_id = ? AND status = 'scheduled'
                ''', (task_id, user_id))
            
            logger.info(f"✅ Cancelled {cancelled_count} reminders for task {task_id}")
            return cancelled_count
            
        except Exception as e:
            logger.error(f"❌ Failed to cancel task reminders: {e}")
            return 0
    
    def reschedule_task_reminders(
        self, 
        task_data: Dict[str, Any], 
        user_fcm_token: str,
        user_notification_settings: Dict[str, Any] = None
    ) -> List[str]:
        """Reschedule reminders when task is updated"""
        try:
            task_id = task_data.get('id')
            user_id = task_data.get('user_id')
            
            # Cancel existing reminders
            self.cancel_task_reminders(task_id, user_id)
            
            # Schedule new reminders
            return self.schedule_task_reminders(task_data, user_fcm_token, user_notification_settings)
            
        except Exception as e:
            logger.error(f"❌ Failed to reschedule reminders: {e}")
            return []
    
    def get_scheduled_reminders(self, task_id: str = None, user_id: str = None) -> List[Dict[str, Any]]:
        """Get scheduled reminders, optionally filtered by task or user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if task_id and user_id:
                    cursor = conn.execute('''
                        SELECT * FROM scheduled_reminders 
                        WHERE task_id = ? AND user_id = ? AND status = 'scheduled'
                        ORDER BY reminder_time
                    ''', (task_id, user_id))
                elif task_id:
                    cursor = conn.execute('''
                        SELECT * FROM scheduled_reminders 
                        WHERE task_id = ? AND status = 'scheduled'
                        ORDER BY reminder_time
                    ''', (task_id,))
                elif user_id:
                    cursor = conn.execute('''
                        SELECT * FROM scheduled_reminders 
                        WHERE user_id = ? AND status = 'scheduled'
                        ORDER BY reminder_time
                    ''', (user_id,))
                else:
                    cursor = conn.execute('''
                        SELECT * FROM scheduled_reminders 
                        WHERE status = 'scheduled'
                        ORDER BY reminder_time
                    ''')
                
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"❌ Failed to get scheduled reminders: {e}")
            return []
    
    def cleanup_old_reminders(self, days: int = 30):
        """Clean up old reminder records"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    DELETE FROM scheduled_reminders 
                    WHERE created_at < ? AND status IN ('sent', 'failed', 'cancelled')
                ''', (cutoff_date.isoformat(),))
                
                deleted_count = cursor.rowcount
                
            logger.info(f"🧹 Cleaned up {deleted_count} old reminder records")
            return deleted_count
            
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old reminders: {e}")
            return 0
    
    def _parse_reminder_time(self, reminder_data) -> Optional[datetime]:
        """Parse reminder time from various formats"""
        try:
            if isinstance(reminder_data, dict):
                time_str = reminder_data.get('reminder_time') or reminder_data.get('time')
            else:
                time_str = str(reminder_data)
            
            if not time_str:
                return None
                
            # Parse ISO format datetime
            if isinstance(time_str, str):
                return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to parse reminder time: {e}")
            return None
    
    def _should_send_notifications(self, user_settings: Dict[str, Any] = None) -> bool:
        """Check if notifications should be sent based on user settings"""
        if not user_settings:
            return True  # Default to enabled
            
        return user_settings.get('notifications_enabled', True) and \
               user_settings.get('task_reminders_enabled', True)
    
    def _is_quiet_hours(self, reminder_time: datetime, user_settings: Dict[str, Any] = None) -> bool:
        """Check if reminder time falls within user's quiet hours"""
        try:
            if not user_settings:
                return False
                
            quiet_start = user_settings.get('quiet_hours_start', 22)  # 10 PM
            quiet_end = user_settings.get('quiet_hours_end', 8)       # 8 AM
            
            hour = reminder_time.hour
            
            if quiet_start < quiet_end:
                # Same day range (e.g., 8 AM to 10 PM)
                return hour < quiet_start or hour >= quiet_end
            else:
                # Overnight range (e.g., 10 PM to 8 AM)
                return hour >= quiet_start or hour < quiet_end
                
        except Exception as e:
            logger.warning(f"Failed to check quiet hours: {e}")
            return False

# Global reminder scheduler instance
reminder_scheduler = ReminderScheduler()