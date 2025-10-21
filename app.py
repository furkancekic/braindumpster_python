from flask import Flask, jsonify, render_template
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import DevelopmentConfig, ProductionConfig, get_config, validate_config
from services.firebase_service import FirebaseService
from services.gemini_service import GeminiService
from services.notification_service import NotificationService
from services.scheduler_service import SchedulerService
from services.localization_service import LocalizationService
from routes import auth_bp, chat_bp, tasks_bp
from routes.notifications import notifications_bp, init_notification_services
from routes.audio_storage import audio_storage_bp
from routes.subscriptions import subscriptions_bp
from routes.legal import legal_bp
from routes.account_deletion import account_deletion_bp
from routes.users import users_bp
from routes.apple_webhook_routes import apple_webhook_bp
import logging
import sys
import os
from datetime import datetime

def setup_logging():
    """Setup detailed logging for the application"""
    # Create custom formatter
    class ColoredFormatter(logging.Formatter):
        COLORS = {
            'DEBUG': '\033[36m',    # Cyan
            'INFO': '\033[32m',     # Green
            'WARNING': '\033[33m',  # Yellow
            'ERROR': '\033[31m',    # Red
            'CRITICAL': '\033[35m', # Magenta
        }
        RESET = '\033[0m'
        
        def format(self, record):
            # Add timestamp and user context
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            color = self.COLORS.get(record.levelname, '')
            reset = self.RESET
            
            # Format: [TIMESTAMP] [LEVEL] [MODULE] MESSAGE
            return f"{color}[{timestamp}] [{record.levelname}] [{record.name}] {record.getMessage()}{reset}"
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(console_handler)
    
    # Specific loggers for our modules
    app_logger = logging.getLogger('braindumpster')
    app_logger.setLevel(logging.DEBUG)
    
    print(f"\n🚀 BRAINDUMPSTER LOGGING INITIALIZED - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

def create_app(config_name=None):
    # Setup logging first
    setup_logging()
    logger = logging.getLogger('braindumpster.app')
    
    app = Flask(__name__)
    
    # Load configuration based on environment
    if config_name == 'production' or os.environ.get('FLASK_ENV') == 'production':
        app.config.from_object(ProductionConfig)
        logger.info("🏭 Running in PRODUCTION mode")
        config_class = ProductionConfig
    else:
        app.config.from_object(DevelopmentConfig)
        logger.info("🔧 Running in DEVELOPMENT mode")
        config_class = DevelopmentConfig

    # Validate configuration at boot
    try:
        validate_config(config_class)
        logger.info("✅ Configuration validation passed")
    except ValueError as e:
        logger.error(f"❌ Configuration validation failed: {e}")
        raise RuntimeError(f"Application cannot start due to configuration errors: {e}")
    
    logger.info("🔧 Creating Flask application...")
    
    # Enable CORS for Flutter integration
    if hasattr(app.config, 'CORS_ORIGINS') and app.config['CORS_ORIGINS']:
        # Production CORS with specific origins
        CORS(app, resources={
            r"/api/*": {
                "origins": app.config['CORS_ORIGINS'],
                "methods": ["GET", "POST", "PUT", "DELETE"],
                "allow_headers": ["Content-Type", "Authorization"]
            },
            r"/subscriptions/*": {
                "origins": app.config['CORS_ORIGINS'],
                "methods": ["GET", "POST", "PUT", "DELETE"],
                "allow_headers": ["Content-Type", "Authorization"]
            }
        })
        logger.info(f"🌐 CORS configured for production origins: {app.config['CORS_ORIGINS']}")
    else:
        # Development CORS allowing all origins
        CORS(app, resources={
            r"/api/*": {
                "origins": "*",
                "methods": ["GET", "POST", "PUT", "DELETE"],
                "allow_headers": ["Content-Type", "Authorization"]
            },
            r"/subscriptions/*": {
                "origins": "*",
                "methods": ["GET", "POST", "PUT", "DELETE"],
                "allow_headers": ["Content-Type", "Authorization"]
            }
        })
        logger.info("🌐 CORS configured for development (all origins)")
    
    # Rate limiting
    if app.config.get('ENABLE_RATELIMIT', True):
        limiter = Limiter(
            app,
            key_func=get_remote_address,
            default_limits=["1000 per hour", "100 per minute"],
            storage_uri=app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
        )
        logger.info(f"⚡ Rate limiting enabled with storage: {app.config.get('RATELIMIT_STORAGE_URL', 'memory://')}")
    else:
        logger.warning("⚠️ Rate limiting is disabled")
    
    # Initialize services
    logger.info("🔥 Initializing Firebase service...")
    app.firebase_service = FirebaseService()
    
    logger.info("🤖 Initializing Gemini service...")
    app.gemini_service = GeminiService()
    
    logger.info("📱 Initializing Notification service...")
    app.notification_service = NotificationService(app.firebase_service)
    
    logger.info("⏰ Initializing Scheduler service...")
    app.scheduler_service = SchedulerService(app.firebase_service, app.notification_service)
    
    logger.info("🌍 Initializing Localization service...")
    app.localization_service = LocalizationService()
    
    # Start the scheduler
    try:
        app.scheduler_service.start()
        logger.info("✅ Background scheduler started successfully")
    except Exception as e:
        logger.error(f"❌ Failed to start scheduler: {e}")
        logger.warning("⚠️ Continuing without background scheduling")
    
    # Initialize notification services for the blueprint
    init_notification_services(
        app.firebase_service, 
        app.notification_service, 
        app.scheduler_service
    )
    
    # Register blueprints
    logger.info("📋 Registering API blueprints...")
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')
    app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
    app.register_blueprint(notifications_bp, url_prefix='/api/notifications')
    app.register_blueprint(audio_storage_bp, url_prefix='/api/audio')
    app.register_blueprint(subscriptions_bp, url_prefix='/api/subscriptions')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(apple_webhook_bp)  # Apple webhook (already has /api/webhooks prefix)
    app.register_blueprint(legal_bp, url_prefix='/legal')
    app.register_blueprint(account_deletion_bp)
    logger.info("✅ All blueprints registered successfully")
    
    # Add request logging middleware
    @app.before_request
    def log_request_info():
        from flask import request
        request_logger = logging.getLogger('braindumpster.requests')
        request_logger.info(f"📥 {request.method} {request.path} from {request.remote_addr}")

        # Only log detailed request data in development mode
        if app.config.get('DEBUG', True):
            # Only try to parse JSON for POST/PUT requests
            if request.method in ['POST', 'PUT', 'PATCH']:
                try:
                    if request.json:
                        request_logger.debug(f"📦 Request body: {request.json}")
                except Exception:
                    # Don't log errors for non-JSON requests
                    pass
            elif request.args:
                request_logger.debug(f"📦 Query params: {dict(request.args)}")
    
    @app.after_request
    def log_response_info(response):
        response_logger = logging.getLogger('braindumpster.responses')
        if response.status_code >= 400:
            response_logger.error(f"📤 {response.status_code} {response.status}")
            # Only log response details in development mode
            if app.config.get('DEBUG', True) and response.data:
                response_logger.debug(f"💥 Error response: {response.get_data(as_text=True)}")
        else:
            response_logger.info(f"📤 {response.status_code} {response.status}")
        return response
    
    # Global error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        from flask import request
        logger.error(f"🔍 404 Not Found: {request.path}")

        if app.config.get('DEBUG', True):
            # Development mode: show available endpoints
            return jsonify({
                "error": "Endpoint not found",
                "path": request.path,
                "available_endpoints": [
                    "/api/health",
                    "/api/tasks/user/<user_id>",
                    "/api/tasks/stats/<user_id>",
                    "/api/tasks/create",
                    "/api/chat/message",
                    "/api/auth/*",
                    "/api/notifications/register-token",
                    "/api/notifications/test-notification",
                    "/api/notifications/preferences",
                    "/api/notifications/health"
                ]
            }), 404
        else:
            # Production mode: generic message
            return jsonify({
                "error": "Endpoint not found"
            }), 404
    
    @app.errorhandler(405)
    def method_not_allowed_error(error):
        from flask import request
        logger.error(f"🚫 405 Method Not Allowed: {request.method} {request.path}")
        return jsonify({
            "error": "Method not allowed",
            "method": request.method,
            "path": request.path
        }), 405
    
    @app.errorhandler(500)
    def internal_server_error(error):
        logger.error(f"💥 500 Internal Server Error: {str(error)}")

        if app.config.get('DEBUG', True):
            # Development mode: show error details
            return jsonify({
                "error": "Internal server error",
                "message": str(error)
            }), 500
        else:
            # Production mode: generic message
            return jsonify({
                "error": "Internal server error"
            }), 500
    
    # Web interface routes
    @app.route('/')
    def index():
        return render_template('chat.html')
    
    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')
    
    # Health check for Flutter
    @app.route('/api/health', methods=['GET'])
    def health_check():
        logger.info("💓 Health check requested")
        try:
            if app.config.get('DEBUG', True):
                # Development mode: detailed health check
                health_data = {
                    "status": "healthy",
                    "message": "Braindumpster API is running",
                    "timestamp": datetime.now().isoformat(),
                    "environment": "development",
                    "services": {
                        "firebase": "disconnected",
                        "gemini": "disconnected",
                        "notifications": "disconnected",
                        "scheduler": "stopped"
                    },
                    "connection_tests": {}
                }

                # Test Firebase connection
                if hasattr(app, 'firebase_service'):
                    try:
                        if app.firebase_service.health_check():
                            health_data["services"]["firebase"] = "connected"
                            health_data["connection_tests"]["firebase"] = "✅ Healthy"
                        else:
                            health_data["services"]["firebase"] = "unhealthy"
                            health_data["connection_tests"]["firebase"] = "❌ Connection failed"
                    except Exception as e:
                        health_data["services"]["firebase"] = "error"
                        health_data["connection_tests"]["firebase"] = f"❌ {str(e)}"

                # Test Gemini connection
                if hasattr(app, 'gemini_service'):
                    try:
                        if app.gemini_service.health_check():
                            health_data["services"]["gemini"] = "connected"
                            health_data["connection_tests"]["gemini"] = "✅ Healthy"
                        else:
                            health_data["services"]["gemini"] = "unhealthy"
                            health_data["connection_tests"]["gemini"] = "❌ Connection failed"
                    except Exception as e:
                        health_data["services"]["gemini"] = "error"
                        health_data["connection_tests"]["gemini"] = f"❌ {str(e)}"

                # Test notification service
                if hasattr(app, 'notification_service'):
                    health_data["services"]["notifications"] = "connected"
                    health_data["connection_tests"]["notifications"] = "✅ Service available"

                # Test scheduler service
                if (hasattr(app, 'scheduler_service') and
                    app.scheduler_service.scheduler and
                    app.scheduler_service.scheduler.running):
                    health_data["services"]["scheduler"] = "running"
                    health_data["connection_tests"]["scheduler"] = "✅ Running"

                health_data["debug_info"] = {
                    "cors_origins": getattr(app.config, 'CORS_ORIGINS', 'all'),
                    "rate_limiting": app.config.get('ENABLE_RATELIMIT', False)
                }

                # Determine overall health status
                all_services_healthy = all(
                    status in ["connected", "running"]
                    for status in health_data["services"].values()
                )

                if not all_services_healthy:
                    health_data["status"] = "degraded"
                    health_data["message"] = "Some services are not fully operational"

                return jsonify(health_data), 200
            else:
                # Production mode: minimal health check
                # Quick basic service checks for critical functionality
                firebase_ok = hasattr(app, 'firebase_service')
                scheduler_ok = (hasattr(app, 'scheduler_service') and
                              app.scheduler_service.scheduler and
                              app.scheduler_service.scheduler.running)

                if firebase_ok and scheduler_ok:
                    return jsonify({
                        "status": "healthy",
                        "timestamp": datetime.now().isoformat()
                    }), 200
                else:
                    return jsonify({
                        "status": "degraded",
                        "timestamp": datetime.now().isoformat()
                    }), 503

        except Exception as e:
            logger.error(f"❌ Health check failed: {str(e)}")
            if app.config.get('DEBUG', True):
                return jsonify({
                    "status": "unhealthy",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat()
                }), 500
            else:
                return jsonify({
                    "status": "unhealthy",
                    "timestamp": datetime.now().isoformat()
                }), 500
    
    # Security headers for production
    @app.after_request
    def after_request(response):
        if not app.config.get('DEBUG', True):
            # Production security headers
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response
    
    # Add shutdown handler
    import atexit
    def shutdown_handler():
        logger.info("🛑 Application shutting down...")
        if hasattr(app, 'scheduler_service'):
            try:
                app.scheduler_service.shutdown()
                logger.info("✅ Scheduler shutdown completed")
            except Exception as e:
                logger.error(f"❌ Error during scheduler shutdown: {e}")
    
    atexit.register(shutdown_handler)
    
    logger.info("🎉 Flask application created successfully!")
    return app

if __name__ == '__main__':
    app = create_app()
    # Security: Only bind to localhost in debug mode, never expose publicly
    # Allow connections from any network interface (needed for mobile development)
    # Using port 5001 to avoid conflicts with AirPlay Receiver
    app.run(debug=True, host='0.0.0.0', port=5001)