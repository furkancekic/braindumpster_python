import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor
import atexit
import pytz
import os

from models.task import Task, TaskStatus, Reminder
from services.firebase_service import FirebaseService
from services.notification_service import NotificationService

# Configure logging with file handler
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add file handler for scheduler logs
log_dir = '/var/www/braindumpster/braindumpster_python/logs'
os.makedirs(log_dir, exist_ok=True)
file_handler = logging.FileHandler(os.path.join(log_dir, 'reminders.log'))
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)
logger.info("📝 Scheduler logging to reminders.log initialized")

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
            logger.info(f"📋 ========== PROCESSING DUE REMINDERS ==========")
            logger.info(f"⏰ Current time (UTC): {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # Get all users
            users = self.firebase_service.get_all_users()
            logger.info(f"👥 Found {len(users)} users to check")

            total_processed = 0
            total_sent = 0
            total_failed = 0

            for user in users:
                try:
                    logger.info(f"\n🔍 Checking reminders for user: {user['id']}")

                    # Get active reminders for this user
                    due_reminders = self.firebase_service.get_due_reminders(
                        user_id=user['id'],
                        current_time=current_time
                    )

                    if not due_reminders:
                        logger.info(f"   ✓ No due reminders for this user")
                        continue

                    logger.info(f"   📬 Found {len(due_reminders)} due reminder(s)")

                    for reminder_data in due_reminders:
                        total_processed += 1
                        logger.info(f"\n   📌 Processing reminder #{total_processed}:")
                        logger.info(f"      Reminder ID: {reminder_data['reminder_id']}")
                        logger.info(f"      Task ID: {reminder_data['task_id']}")

                        # Get the full task data
                        task_data = self.firebase_service.get_task(reminder_data['task_id'])
                        if not task_data:
                            logger.warning(f"      ❌ Task not found: {reminder_data['task_id']}")
                            total_failed += 1
                            continue

                        # Convert to Task object
                        task = Task.from_dict(task_data)
                        logger.info(f"      Task title: '{task.title}'")
                        logger.info(f"      Task status: {task.status}")

                        # Skip if task is not approved or is completed
                        if task.status not in [TaskStatus.APPROVED, TaskStatus.PENDING]:
                            logger.info(f"      ⏭️  Skipping - task status is '{task.status}' (not approved/pending)")
                            continue

                        # Find the specific reminder
                        reminder = None
                        for r in task.reminders:
                            if r.id == reminder_data['reminder_id'] and not r.sent:
                                # Ensure timezone-aware comparison
                                rt = r.reminder_time
                                if rt.tzinfo is None:
                                    # If somehow naive, assume UTC
                                    rt = rt.replace(tzinfo=pytz.UTC)
                                    logger.warning(f"      ⚠️ Reminder time was naive, assumed UTC: {rt}")

                                ct = current_time
                                if ct.tzinfo is None:
                                    ct = ct.replace(tzinfo=pytz.UTC)

                                # Now safe to compare
                                if rt <= ct:
                                    reminder = r
                                    logger.info(f"      ✅ Matched reminder in task")
                                    logger.info(f"         Reminder time: {rt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                                break

                        if not reminder:
                            logger.warning(f"      ❌ No matching unsent reminder found for {reminder_data['reminder_id']}")
                            total_failed += 1
                            continue

                        # Check if reminder is too old (fail-safe cleanup)
                        # Ensure timezone-aware for time_diff calculation
                        rt_for_diff = reminder.reminder_time
                        if rt_for_diff.tzinfo is None:
                            rt_for_diff = rt_for_diff.replace(tzinfo=pytz.UTC)
                        ct_for_diff = current_time
                        if ct_for_diff.tzinfo is None:
                            ct_for_diff = ct_for_diff.replace(tzinfo=pytz.UTC)

                        time_diff = ct_for_diff - rt_for_diff
                        minutes_old = int(time_diff.total_seconds()/60)
                        logger.info(f"      ⏱️  Reminder is {minutes_old} minutes old")

                        if time_diff.total_seconds() > 3600:  # 1 hour old
                            logger.warning(f"      ⚠️  FAIL-SAFE: Reminder too old ({minutes_old} min), marking as sent without notification")
                            self.firebase_service.mark_reminder_as_sent(
                                task_id=task.id,
                                reminder_id=reminder.id
                            )

                            # Update task object
                            for r in task.reminders:
                                if r.id == reminder.id:
                                    r.sent = True
                                    break

                            # Check if task should be auto-completed
                            self.check_and_auto_complete_task(task)
                            total_failed += 1
                            continue

                        # Send notification
                        logger.info(f"      📤 Attempting to send notification...")
                        success = self.notification_service.send_reminder_notification(reminder, task)

                        if success:
                            logger.info(f"      ✅ Notification sent successfully!")
                            # Mark reminder as sent
                            self.firebase_service.mark_reminder_as_sent(
                                task_id=task.id,
                                reminder_id=reminder.id
                            )
                            total_sent += 1

                            # Update the task object to reflect the reminder was sent
                            for r in task.reminders:
                                if r.id == reminder.id:
                                    r.sent = True
                                    break

                            # Check if task should be auto-completed
                            self.check_and_auto_complete_task(task)
                        else:
                            logger.error(f"      ❌ FAILED to send notification for task: {task.title}")
                            logger.error(f"         Check notification_service logs for details")
                            total_failed += 1

                except Exception as e:
                    logger.error(f"❌ Error processing reminders for user {user['id']}: {e}")
                    import traceback
                    logger.error(f"   Traceback: {traceback.format_exc()}")
                    continue

            logger.info(f"\n{'='*60}")
            logger.info(f"📊 REMINDER PROCESSING SUMMARY:")
            logger.info(f"   Total processed: {total_processed}")
            logger.info(f"   Successfully sent: {total_sent}")
            logger.info(f"   Failed: {total_failed}")
            logger.info(f"{'='*60}\n")

        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR in process_due_reminders: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")
    
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

    def check_and_auto_complete_task(self, task: Task):
        """
        Check if a task should be auto-completed based on reminders.
        A task is auto-completed if:
        1. It has NO due_date
        2. ALL reminders have been sent
        """
        try:
            # Check if task has a due_date
            if task.due_date:
                logger.debug(f"Task {task.id} has due_date, skipping auto-complete")
                return

            # Check if task has any reminders
            if not task.reminders or len(task.reminders) == 0:
                logger.debug(f"Task {task.id} has no reminders, skipping auto-complete")
                return

            # Check if all reminders have been sent
            all_reminders_sent = all(reminder.sent for reminder in task.reminders)

            if all_reminders_sent:
                logger.info(f"🎯 Auto-completing task {task.id} ({task.title}) - all reminders sent, no due_date")

                # Update task status to COMPLETED
                from datetime import datetime
                try:
                    self.firebase_service.update_task(
                        task_id=task.id,
                        updates={
                            'status': TaskStatus.COMPLETED.value,
                            'completed_at': datetime.utcnow().isoformat(),
                            'updated_at': datetime.utcnow().isoformat(),
                            'auto_completed': True
                        }
                    )
                    success = True
                except Exception as e:
                    logger.error(f"❌ Failed to update task: {e}")
                    success = False

                if success:
                    logger.info(f"✅ Task {task.id} auto-completed successfully")

                    # Send task completion notification
                    try:
                        self.notification_service.send_task_completion_notification(task)
                        logger.info(f"📱 Completion notification sent for task {task.id}")
                    except Exception as notif_error:
                        logger.error(f"Failed to send completion notification: {notif_error}")
                else:
                    logger.error(f"❌ Failed to auto-complete task {task.id}")
            else:
                sent_count = sum(1 for r in task.reminders if r.sent)
                logger.debug(f"Task {task.id} has {sent_count}/{len(task.reminders)} reminders sent")

        except Exception as e:
            logger.error(f"Error in check_and_auto_complete_task for task {task.id}: {e}")