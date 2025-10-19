import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor
import atexit
import pytz

from models.task import Task, TaskStatus, Reminder
from services.firebase_service import FirebaseService
from services.notification_service import NotificationService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SchedulerService:
    """Service for managing background tasks and notification scheduling"""
    
    def __init__(self, firebase_service: FirebaseService, notification_service: NotificationService):
        self.firebase_service = firebase_service
        self.notification_service = notification_service
        self.scheduler = None
        self._initialize_scheduler()
    
    def _initialize_scheduler(self):
        """Initialize the APScheduler with proper configuration"""
        try:
            # Configure executor
            executors = {
                'default': ThreadPoolExecutor(20),
            }
            
            # Job defaults
            job_defaults = {
                'coalesce': False,
                'max_instances': 3
            }
            
            # Create scheduler
            self.scheduler = BackgroundScheduler(
                executors=executors,
                job_defaults=job_defaults,
                timezone=pytz.UTC
            )
            
            logger.info("Scheduler initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {e}")
            raise
    
    def start(self):
        """Start the scheduler and add recurring jobs"""
        try:
            if self.scheduler and not self.scheduler.running:
                self.scheduler.start()
                
                # Add recurring jobs
                self._add_recurring_jobs()
                
                # Register shutdown handler
                atexit.register(self.shutdown)
                
                logger.info("Scheduler started successfully")
            else:
                logger.warning("Scheduler is already running")
                
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise
    
    def shutdown(self):
        """Shutdown the scheduler gracefully"""
        try:
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                logger.info("Scheduler shutdown successfully")
        except Exception as e:
            logger.error(f"Error during scheduler shutdown: {e}")
    
    def _add_recurring_jobs(self):
        """Add recurring background jobs"""
        try:
            # Check for due reminders every minute
            self.scheduler.add_job(
                func=self.process_due_reminders,
                trigger=IntervalTrigger(minutes=1),
                id='check_due_reminders',
                name='Check for due reminders',
                replace_existing=True
            )
            
            # Send daily summaries at 8 AM
            self.scheduler.add_job(
                func=self.send_daily_summaries,
                trigger=CronTrigger(hour=8, minute=0),
                id='daily_summaries',
                name='Send daily summaries',
                replace_existing=True
            )
            
            # Cleanup completed tasks older than 30 days at midnight
            self.scheduler.add_job(
                func=self.cleanup_old_tasks,
                trigger=CronTrigger(hour=0, minute=0),
                id='cleanup_old_tasks',
                name='Cleanup old completed tasks',
                replace_existing=True
            )
            
            # Health check every 5 minutes
            self.scheduler.add_job(
                func=self.health_check,
                trigger=IntervalTrigger(minutes=5),
                id='health_check',
                name='System health check',
                replace_existing=True
            )
            
            logger.info("Recurring jobs added successfully")
            
        except Exception as e:
            logger.error(f"Failed to add recurring jobs: {e}")
            raise
    
    def process_due_reminders(self):
        """Process all due reminders and send notifications"""
        try:
            current_time = datetime.now(pytz.UTC)
            logger.info(f"Processing due reminders at {current_time}")
            
            # Get all users
            users = self.firebase_service.get_all_users()
            
            total_processed = 0
            total_sent = 0
            
            for user in users:
                try:
                    # Get active reminders for this user
                    due_reminders = self.firebase_service.get_due_reminders(
                        user_id=user['id'],
                        current_time=current_time
                    )
                    
                    for reminder_data in due_reminders:
                        total_processed += 1
                        logger.debug(f"🔍 Processing reminder {total_processed}: {reminder_data['reminder_id']} for task {reminder_data['task_id']}")
                        
                        # Get the full task data
                        task_data = self.firebase_service.get_task(reminder_data['task_id'])
                        if not task_data:
                            logger.warning(f"Task not found: {reminder_data['task_id']}")
                            continue
                        
                        # Convert to Task object
                        task = Task.from_dict(task_data)
                        
                        # Skip if task is not approved or is completed
                        if task.status not in [TaskStatus.APPROVED, TaskStatus.PENDING]:
                            logger.debug(f"⏭️ Skipping reminder for task {task.id} - status: {task.status}")
                            continue
                        
                        # Find the specific reminder
                        reminder = None
                        for r in task.reminders:
                            logger.debug(f"🔍 Checking reminder {r.id} vs {reminder_data['reminder_id']}, sent: {r.sent}, time: {r.reminder_time}")
                            if (r.id == reminder_data['reminder_id'] and 
                                not r.sent and 
                                r.reminder_time <= current_time):
                                reminder = r
                                logger.debug(f"✅ Found matching reminder: {r.id}")
                                break
                        
                        if not reminder:
                            logger.debug(f"❌ No matching reminder found for {reminder_data['reminder_id']}")
                            continue
                        
                        # Send notification
                        success = self.notification_service.send_reminder_notification(reminder, task)
                        
                        if success:
                            # Mark reminder as sent
                            self.firebase_service.mark_reminder_as_sent(
                                task_id=task.id,
                                reminder_id=reminder.id
                            )
                            total_sent += 1
                            logger.info(f"Reminder sent for task: {task.title}")
                        else:
                            logger.error(f"Failed to send reminder for task: {task.title}")
                            
                except Exception as e:
                    logger.error(f"Error processing reminders for user {user['id']}: {e}")
                    continue
            
            logger.info(f"Reminder processing complete: {total_sent}/{total_processed} sent successfully")
            
        except Exception as e:
            logger.error(f"Error in process_due_reminders: {e}")
    
    def send_daily_summaries(self):
        """Send daily task summaries to all users"""
        try:
            logger.info("Sending daily summaries")
            
            # Get all users
            users = self.firebase_service.get_all_users()
            
            for user in users:
                try:
                    user_id = user['id']
                    
                    # Get user's task statistics for today
                    summary_data = self.firebase_service.get_user_daily_stats(user_id)
                    
                    # Only send summary if user has pending tasks or completed tasks today
                    if summary_data.get('pending_tasks', 0) > 0 or summary_data.get('completed_tasks', 0) > 0:
                        success = self.notification_service.send_daily_summary_notification(
                            user_id=user_id,
                            summary_data=summary_data
                        )
                        
                        if success:
                            logger.info(f"Daily summary sent to user: {user_id}")
                        else:
                            logger.error(f"Failed to send daily summary to user: {user_id}")
                            
                except Exception as e:
                    logger.error(f"Error sending daily summary to user {user['id']}: {e}")
                    continue
            
            logger.info("Daily summaries processing complete")
            
        except Exception as e:
            logger.error(f"Error in send_daily_summaries: {e}")
    
    def cleanup_old_tasks(self):
        """Clean up completed tasks older than 30 days"""
        try:
            logger.info("Starting cleanup of old completed tasks")
            
            cutoff_date = datetime.now(pytz.UTC) - timedelta(days=30)
            
            # Get all users
            users = self.firebase_service.get_all_users()
            
            total_cleaned = 0
            
            for user in users:
                try:
                    user_id = user['id']
                    
                    # Get old completed tasks for this user
                    old_tasks = self.firebase_service.get_old_completed_tasks(
                        user_id=user_id,
                        cutoff_date=cutoff_date
                    )
                    
                    for task in old_tasks:
                        # Archive task instead of deleting (soft delete)
                        success = self.firebase_service.archive_task(task['id'])
                        if success:
                            total_cleaned += 1
                            
                except Exception as e:
                    logger.error(f"Error cleaning up tasks for user {user['id']}: {e}")
                    continue
            
            logger.info(f"Cleanup complete: {total_cleaned} tasks archived")
            
        except Exception as e:
            logger.error(f"Error in cleanup_old_tasks: {e}")
    
    def health_check(self):
        """Perform system health checks"""
        try:
            # Check database connectivity
            db_healthy = self.firebase_service.health_check()
            
            # Check scheduler status
            scheduler_healthy = self.scheduler.running if self.scheduler else False
            
            # Log health status
            if db_healthy and scheduler_healthy:
                logger.debug("System health check: All systems operational")
            else:
                logger.warning(f"System health check: DB={db_healthy}, Scheduler={scheduler_healthy}")
                
        except Exception as e:
            logger.error(f"Error in health_check: {e}")
    
    def schedule_reminder_for_task(self, task: Task):
        """Schedule all reminders for a specific task"""
        try:
            if task.status not in [TaskStatus.APPROVED, TaskStatus.PENDING]:
                logger.info(f"Task {task.id} is not approved/pending, skipping reminder scheduling")
                return
            
            current_time = datetime.now(pytz.UTC)
            scheduled_count = 0
            
            for reminder in task.reminders:
                if not reminder.sent and reminder.reminder_time > current_time:
                    # This will be handled by the recurring job
                    scheduled_count += 1
            
            logger.info(f"Task {task.id} has {scheduled_count} reminders that will be processed by scheduler")
            
        except Exception as e:
            logger.error(f"Error scheduling reminders for task {task.id}: {e}")
    
    def reschedule_reminders_for_task(self, task_id: str):
        """Reschedule reminders for a task after it's been modified"""
        try:
            # Get updated task data
            task_data = self.firebase_service.get_task(task_id)
            if not task_data:
                logger.warning(f"Task not found for rescheduling: {task_id}")
                return
            
            task = Task.from_dict(task_data)
            self.schedule_reminder_for_task(task)
            
        except Exception as e:
            logger.error(f"Error rescheduling reminders for task {task_id}: {e}")
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get current scheduler status and job information"""
        try:
            if not self.scheduler:
                return {"status": "not_initialized"}
            
            jobs = []
            for job in self.scheduler.get_jobs():
                jobs.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger)
                })
            
            return {
                "status": "running" if self.scheduler.running else "stopped",
                "jobs": jobs,
                "job_count": len(jobs)
            }
            
        except Exception as e:
            logger.error(f"Error getting scheduler status: {e}")
            return {"status": "error", "error": str(e)}