# AI Task Scheduler Flask Application

A Flask-based web application that uses AI (Google Gemini) to convert natural language requests into structured, actionable tasks with automatic scheduling and reminders.

## Features

- **AI-Powered Task Creation**: Uses Gemini AI to convert natural language into structured tasks
- **Context Awareness**: Maintains conversation history and user context
- **Task Refinement**: Allows users to provide feedback and get refined suggestions
- **Firebase Integration**: Complete user management and data storage
- **Flutter Ready**: RESTful API designed for mobile app integration
- **Web Interface**: Complete chat interface and task dashboard
- **Task Management**: Full CRUD operations with priority and status tracking

## Project Structure

```
task_scheduler/
├── app.py                  # Main Flask application
├── config.py               # Configuration settings
├── requirements.txt        # Python dependencies
├── models/                 # Data models
│   ├── __init__.py
│   ├── user.py
│   ├── task.py
│   └── conversation.py
├── services/               # Business logic services
│   ├── __init__.py
│   ├── gemini_service.py
│   └── firebase_service.py
├── routes/                 # API endpoints
│   ├── __init__.py
│   ├── auth.py
│   ├── chat.py
│   └── tasks.py
├── prompts/                # AI prompt templates
│   ├── __init__.py
│   └── gemini_prompts.py
├── static/                 # Static assets
│   ├── css/
│   └── js/
├── templates/              # HTML templates
│   ├── base.html
│   ├── chat.html
│   └── dashboard.html
└── firebase_config.json   # Firebase credentials
```

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd braindumpster
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

4. **Set up Firebase**:
   - Create a Firebase project
   - Download the service account key
   - Rename it to `firebase_config.json`
   - Update `config.py` with your Firebase configuration

5. **Set up Gemini AI**:
   - Get a Gemini API key from Google AI Studio
   - Update the `GEMINI_API_KEY` in `config.py`

## Running the Application

1. **Development mode**:
   ```bash
   python app.py
   ```

2. **Production mode**:
   ```bash
   gunicorn app:create_app()
   ```

3. **Access the application**:
   - Web interface: `http://localhost:5000`
   - Dashboard: `http://localhost:5000/dashboard`
   - API health check: `http://localhost:5000/api/health`

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/verify` - Verify Firebase ID token
- `GET /api/auth/profile/<user_id>` - Get user profile

### Chat
- `POST /api/chat/send` - Send message and get AI response
- `GET /api/chat/conversations/<user_id>` - Get user's conversations
- `POST /api/chat/refine` - Refine tasks based on feedback

### Tasks
- `POST /api/tasks/create` - Create new tasks
- `GET /api/tasks/user/<user_id>` - Get user's tasks
- `PUT /api/tasks/<task_id>` - Update task
- `DELETE /api/tasks/<task_id>` - Delete task
- `POST /api/tasks/approve` - Approve multiple tasks
- `GET /api/tasks/stats/<user_id>` - Get task statistics

## Usage

1. **Chat Interface**: 
   - Go to the main page and start chatting with the AI
   - Describe what you want to accomplish
   - Review and approve the generated tasks

2. **Dashboard**:
   - View all your tasks and their status
   - Update task status (approve, complete, cancel)
   - Filter tasks by status
   - View task statistics

## Configuration

### Environment Variables
- `SECRET_KEY`: Flask secret key for sessions
- `GEMINI_API_KEY`: Google Gemini AI API key
- `FLASK_ENV`: Development or production environment

### Firebase Configuration
Update `config.py` with your Firebase project details:
- Project ID
- API Key
- Auth Domain
- Database URL
- Storage Bucket

## Account Deletion & Data Privacy

This application includes comprehensive GDPR/KVKK compliant account deletion functionality.

### Account Deletion API Endpoints

#### Request Deletion
- `POST /api/v1/account/deletion/request` - Initiate account deletion process
- `POST /api/v1/account/deletion/confirm` - Confirm deletion with verification code
- `GET /api/v1/account/deletion/status` - Check deletion progress

#### Data Export
- `GET /api/v1/account/data/export` - Export user data before deletion

### Running Deletion Jobs Locally

1. **Start the Flask application**:
   ```bash
   python app.py
   ```

2. **Test deletion flow**:
   ```bash
   # Request deletion
   curl -X POST http://localhost:5000/api/v1/account/deletion/request \
     -H "Authorization: Bearer YOUR_FIREBASE_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"confirmation": "I understand this action cannot be undone"}'

   # Check email for verification code, then confirm
   curl -X POST http://localhost:5000/api/v1/account/deletion/confirm \
     -H "Authorization: Bearer YOUR_FIREBASE_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"request_id": "REQUEST_ID", "verification_code": "CODE"}'
   ```

3. **Monitor deletion progress**:
   ```bash
   curl -X GET "http://localhost:5000/api/v1/account/deletion/status?request_id=REQUEST_ID" \
     -H "Authorization: Bearer YOUR_FIREBASE_TOKEN"
   ```

### Environment Variables for Account Deletion

Add these to your `.env` file:

```bash
# Email service for verification codes
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Third-party service cleanup toggles
ENABLE_REVENUECAT_DELETION=true
ENABLE_FIREBASE_ANALYTICS_DELETION=true
ENABLE_GEMINI_DATA_CLEANUP=true

# Deletion job configuration
DELETION_VERIFICATION_CODE_EXPIRY=900  # 15 minutes in seconds
DELETION_RATE_LIMIT_HOURS=1            # 1 deletion request per hour
DELETION_RETENTION_DAYS=30             # Complete deletion within 30 days

# Legal document hosting
LEGAL_DOCS_CACHE_DURATION=3600         # 1 hour cache for legal documents
```

### Third-Party Service Deletion Toggles

Control which third-party services are included in the deletion process:

#### RevenueCat Deletion
```bash
ENABLE_REVENUECAT_DELETION=true  # Deletes subscription and purchase data
```

#### Firebase Analytics Deletion
```bash
ENABLE_FIREBASE_ANALYTICS_DELETION=true  # Requests user data deletion from Firebase Analytics
```

#### Google Gemini AI Cleanup
```bash
ENABLE_GEMINI_DATA_CLEANUP=true  # Ensures no residual voice processing data
```

### Data Categories Deleted

When account deletion is confirmed, the following data is permanently removed:

1. **User Profile Data**
   - Email address, user preferences, profile settings
   - Account creation date and metadata

2. **Task & Conversation Data**
   - All user-created tasks and reminders
   - Chat conversation history with AI
   - Voice recordings and transcriptions

3. **Subscription Data**
   - RevenueCat customer records
   - Purchase history and receipts

4. **Analytics Data**
   - Firebase Analytics user data
   - App usage patterns and metrics

5. **Third-Party Data**
   - Push notification tokens
   - Cloud storage files and backups

### Legal Compliance Features

- **GDPR Article 17 (Right to Erasure)**: Complete data deletion within 30 days
- **KVKK Article 7**: User rights to deletion and data portability
- **Apple App Store Requirements**: Prominent deletion access in app settings

### Monitoring & Logging

Deletion operations are logged without PII for audit purposes:

```python
# Example log entries (PII redacted)
logger.info(f"Deletion request initiated for user: {mask_user_id(user_id)}")
logger.info(f"Deletion job completed successfully: {job_id}")
logger.error(f"Third-party deletion failed: {service_name} - {error_code}")
```

### Testing Account

For App Store review and testing:
- **Email**: reviewer@braindumpster.com
- **Password**: ReviewTest2025!
- **Note**: This account has pre-populated data for testing the deletion flow

## Flutter Integration

This backend is designed to work seamlessly with Flutter apps:
- CORS enabled for cross-origin requests
- RESTful API design
- JSON responses
- Firebase authentication
- Comprehensive error handling

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.