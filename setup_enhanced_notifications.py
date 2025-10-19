"""
Setup script to integrate the enhanced notification system into the existing app
This file shows how to modify your app.py to include the new notification system
"""
import logging
from integration.notification_integration import (
    notification_integration, 
    integrate_with_existing_scheduler,
    patch_existing_endpoints,
    setup_notification_endpoints
)

logger = logging.getLogger(__name__)

def setup_enhanced_notifications(app):
    """
    Complete setup for the enhanced notification system
    Call this function from your app.py after initializing services
    """
    try:
        logger.info("🚀 Setting up enhanced notification system...")
        
        # 1. Initialize the notification integration with existing services
        scheduler_service = getattr(app, 'scheduler_service', None)
        notification_integration.initialize(app, scheduler_service)
        
        # 2. Integrate with existing scheduler service
        if scheduler_service:
            integrate_with_existing_scheduler(scheduler_service)
        
        # 3. Patch existing endpoints to handle notification cleanup
        patch_existing_endpoints(app)
        
        # 4. Add new notification endpoints
        from routes.notifications import notifications_bp
        setup_notification_endpoints(app, notifications_bp)
        
        # 5. Set up periodic cleanup (optional)
        if scheduler_service and hasattr(scheduler_service, 'scheduler'):
            # Add a daily cleanup job
            scheduler_service.scheduler.add_job(
                func=cleanup_old_notifications,
                trigger='cron',
                hour=3,  # Run at 3 AM daily
                minute=0,
                id='daily_notification_cleanup',
                replace_existing=True
            )
        
        logger.info("✅ Enhanced notification system setup completed successfully!")
        logger.info("📱 Features enabled:")
        logger.info("   - Automatic push notifications when tasks are approved")
        logger.info("   - Smart reminder scheduling based on task due dates")
        logger.info("   - Notification cleanup when tasks/reminders are deleted")
        logger.info("   - User notification preferences management")
        logger.info("   - FCM token management and validation")
        logger.info("   - Quiet hours support")
        logger.info("   - Daily summary notifications")
        logger.info("   - Test notification functionality")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to setup enhanced notifications: {e}")
        return False

def cleanup_old_notifications():
    """Periodic cleanup of old notification data"""
    try:
        from services.notification_manager import notification_manager
        notification_manager.cleanup()
        logger.info("🧹 Completed daily notification cleanup")
    except Exception as e:
        logger.error(f"❌ Error in notification cleanup: {e}")

# Instructions for integrating into app.py
INTEGRATION_INSTRUCTIONS = """
To integrate the enhanced notification system into your existing app.py, follow these steps:

1. Add this import at the top of your app.py:
   from setup_enhanced_notifications import setup_enhanced_notifications

2. After initializing all your services (around line 134), add:
   
   # Setup enhanced notification system
   try:
       success = setup_enhanced_notifications(app)
       if success:
           logger.info("🔔 Enhanced notification system active")
       else:
           logger.warning("⚠️ Enhanced notification system failed to initialize")
   except Exception as e:
       logger.error(f"❌ Notification system error: {e}")
       logger.warning("⚠️ Continuing without enhanced notifications")

3. Add Firebase service account configuration to your config.py:
   
   class Config:
       # ... existing config ...
       FIREBASE_SERVICE_ACCOUNT_PATH = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH', 'path/to/service-account.json')

4. Set environment variable:
   export FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/your/firebase-service-account.json

5. Install required dependencies (if not already installed):
   pip install firebase-admin

That's it! The system will automatically:
- Schedule notifications when tasks are approved
- Cancel notifications when tasks are deleted
- Handle FCM token management
- Provide notification settings endpoints
"""

if __name__ == "__main__":
    print("Enhanced Notification System Setup Guide")
    print("=" * 50)
    print(INTEGRATION_INSTRUCTIONS)