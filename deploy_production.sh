#!/bin/bash

# Production deployment script for Braindumpster API
# This script sets up and starts the API server in production mode

set -e  # Exit on any error

echo "🚀 BRAINDUMPSTER API - PRODUCTION DEPLOYMENT"
echo "============================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "📚 Installing production dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check required files
echo "🔍 Checking configuration files..."

if [ ! -f "firebase_config.json" ]; then
    echo "❌ firebase_config.json not found!"
    echo "   Please add your Firebase service account credentials"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating example..."
    cat > .env << EOF
# Production Environment Variables
FLASK_ENV=production
SECRET_KEY=your-secret-key-here-change-this
GEMINI_API_KEY=your-gemini-api-key-here
PORT=5000
HOST=0.0.0.0

# CORS settings (comma-separated)
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Redis for rate limiting (optional)
# REDIS_URL=redis://localhost:6379/0

# Logging
LOG_LEVEL=INFO
EOF
    echo "📝 Please edit .env file with your configuration"
    echo "   Then run this script again"
    exit 1
fi

# Load environment variables
source .env

# Set production environment
export FLASK_ENV=production

echo "🌍 Environment: $FLASK_ENV"
echo "🔑 Using secret key: ${SECRET_KEY:0:10}..."
echo "🤖 Gemini API configured: $([ -n "$GEMINI_API_KEY" ] && echo "✅" || echo "❌")"

# Run with Gunicorn for production
echo "🏭 Starting production server with Gunicorn..."
echo "📍 Server will be available at: http://$HOST:$PORT"
echo "🛡️  Security features enabled:"
echo "   • Rate limiting"
echo "   • CORS protection"
echo "   • Security headers"
echo "   • Authentication required"
echo ""

# Start the server
exec gunicorn --config gunicorn.conf.py "app:create_app('production')"