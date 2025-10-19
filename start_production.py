#!/usr/bin/env python3
"""
Production startup script for Braindumpster API
This script configures and starts the Flask app for production use
"""

import os
import sys
from app import create_app

def main():
    """Start the application in production mode"""
    
    # Set production environment
    os.environ['FLASK_ENV'] = 'production'
    
    # Create production app
    app = create_app('production')
    
    # Production server configuration
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    
    print(f"🚀 Starting Braindumpster API in PRODUCTION mode")
    print(f"🌐 Server: http://{host}:{port}")
    print(f"🔐 Security: Rate limiting enabled")
    print(f"🛡️  CORS: Production origins only")
    print("=" * 50)
    
    # Start the server
    app.run(
        host=host,
        port=port,
        debug=False,
        threaded=True,
        use_reloader=False
    )

if __name__ == '__main__':
    main()