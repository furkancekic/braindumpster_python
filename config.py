import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') or "AIzaSyDMIo6j9svCX7G66Nkmo0XUYrwbznhDi9Y"
    
    # Firebase configuration for client SDK
    FIREBASE_CONFIG = {
        "apiKey": "AIzaSyCIjfY8IDQg4NRgsWF5yEHFTyFYRnJALi4",
        "authDomain": "voicereminder-e1c91.firebaseapp.com",
        "databaseURL": "https://voicereminder-e1c91-default-rtdb.firebaseio.com",
        "projectId": "voicereminder-e1c91",
        "storageBucket": "voicereminder-e1c91.firebasestorage.app",
        "messagingSenderId": "28669271299",
        "appId": "1:28669271299:web:7a951160eae3df5a141d36"
    }
    
    # Firebase Admin SDK configuration
    FIREBASE_PROJECT_ID = "voicereminder-e1c91"
    FIREBASE_SERVICE_ACCOUNT_PATH = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH', 'firebase_config.json')
    
    # FCM Configuration
    FCM_SERVER_KEY = os.environ.get('FCM_SERVER_KEY')  # Optional: Legacy server key
    
    # Subscription settings
    REVENUECAT_API_KEY = os.environ.get('REVENUECAT_API_KEY')
    REVENUECAT_WEBHOOK_SECRET = os.environ.get('REVENUECAT_WEBHOOK_SECRET')
    APPLE_SHARED_SECRET = os.environ.get('APPLE_SHARED_SECRET')
    GOOGLE_SERVICE_ACCOUNT_KEY = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY')
    
    # Notification settings
    NOTIFICATION_SETTINGS = {
        'default_sound': 'default',
        'default_icon': 'ic_notification',
        'default_color': '#2196F3',
        'channel_id': 'voice_planner_tasks',
        'channel_name': 'Task Reminders',
        'channel_description': 'Notifications for task reminders and updates'
    }
    
    # Scheduler settings
    SCHEDULER_SETTINGS = {
        'timezone': 'UTC',
        'job_defaults': {
            'coalesce': False,
            'max_instances': 3
        },
        'executors': {
            'default': {'type': 'threadpool', 'max_workers': 20}
        }
    }
    
class DevelopmentConfig(Config):
    DEBUG = True

    # Rate limiting settings for development
    ENABLE_RATELIMIT = os.environ.get('ENABLE_RATELIMIT', 'false').lower() == 'true'
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'memory://')
    
class ProductionConfig(Config):
    DEBUG = False

    # Security settings - validation moved to validate_config function
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'production-secret-key'

    # Rate limiting (disabled for production to remove Redis dependency)
    ENABLE_RATELIMIT = os.environ.get('ENABLE_RATELIMIT', 'false').lower() == 'true'
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'memory://')

    # CORS settings for production - validation moved to validate_config function
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')
    
    # API settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file upload
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    # Performance
    JSONIFY_PRETTYPRINT_REGULAR = False
    
    # Production notification settings
    NOTIFICATION_SETTINGS = Config.NOTIFICATION_SETTINGS.copy()
    NOTIFICATION_SETTINGS.update({
        'test_mode': False,
        'log_all_notifications': False,
        'batch_size': 500,  # FCM batch size for production
        'retry_attempts': 3
    })
    
    # Enhanced scheduler settings for production
    SCHEDULER_SETTINGS = Config.SCHEDULER_SETTINGS.copy()
    SCHEDULER_SETTINGS.update({
        'job_defaults': {
            'coalesce': True,  # Merge similar jobs in production
            'max_instances': 1,  # Prevent job overlap
            'misfire_grace_time': 30
        }
    })
    
    # Firebase Admin SDK path for production
    FIREBASE_SERVICE_ACCOUNT_PATH = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH', '/etc/firebase/service-account.json')

# Environment-specific configuration loader
def get_config():
    """
    Get configuration based on environment
    """
    env = os.environ.get('FLASK_ENV', 'development').lower()
    
    if env == 'production':
        return ProductionConfig
    else:
        return DevelopmentConfig

# Validation helper
def validate_config(config_class):
    """
    Validate that all required configuration is present
    """
    errors = []

    # Check required environment variables for production
    if config_class == ProductionConfig:
        env = os.environ.get('FLASK_ENV', 'development').lower()
        if env == 'production':
            # Only validate production requirements when actually running in production
            if not os.environ.get('SECRET_KEY'):
                errors.append("SECRET_KEY environment variable is required in production mode")

            cors_origins = os.environ.get('CORS_ORIGINS')
            if not cors_origins or cors_origins == '*':
                errors.append("CORS_ORIGINS environment variable must be set to explicit origins in production mode (not '*')")

    # Check Firebase service account file (only if it should exist)
    firebase_path = config_class.FIREBASE_SERVICE_ACCOUNT_PATH
    if firebase_path != 'firebase_config.json' and not os.path.exists(firebase_path):
        errors.append(f"Firebase service account file not found: {firebase_path}")

    if errors:
        raise ValueError("Configuration validation failed:\n" + "\n".join(errors))

    return True