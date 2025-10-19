# AI Task Scheduler Flask Application

## Project Structure
```
task_scheduler/
├── app.py
├── config.py
├── requirements.txt
├── models/
│   ├── __init__.py
│   ├── user.py
│   ├── task.py
│   └── conversation.py
├── services/
│   ├── __init__.py
│   ├── gemini_service.py
│   ├── firebase_service.py
│   └── notification_service.py
├── routes/
│   ├── __init__.py
│   ├── auth.py
│   ├── chat.py
│   └── tasks.py
├── prompts/
│   ├── __init__.py
│   └── gemini_prompts.py
├── static/
│   ├── css/
│   └── js/
├── templates/
│   ├── base.html
│   ├── chat.html
│   └── dashboard.html
└── firebase_config.json
```

## requirements.txt
```
Flask==2.3.3
Flask-CORS==4.0.0
python-dotenv==1.0.0
google-generativeai==0.3.2
firebase-admin==6.2.0
pyrebase4==4.7.1
APScheduler==3.10.4
requests==2.31.0
gunicorn==21.2.0
```

## config.py
```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    GEMINI_API_KEY = "AIzaSyDMIo6j9svCX7G66Nkmo0XUYrwbznhDi9Y"
    FIREBASE_CONFIG = {
        "apiKey": "your-firebase-api-key",
        "authDomain": "your-project.firebaseapp.com",
        "databaseURL": "https://your-project.firebaseio.com",
        "projectId": "your-project-id",
        "storageBucket": "your-project.appspot.com",
        "messagingSenderId": "your-sender-id",
        "appId": "your-app-id"
    }
    
class DevelopmentConfig(Config):
    DEBUG = True
    
class ProductionConfig(Config):
    DEBUG = False
```

## app.py
```python
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from config import DevelopmentConfig
from services.firebase_service import FirebaseService
from services.gemini_service import GeminiService
from routes import auth_bp, chat_bp, tasks_bp
import logging

def create_app():
    app = Flask(__name__)
    app.config.from_object(DevelopmentConfig)
    
    # Enable CORS for Flutter integration
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    
    # Initialize services
    app.firebase_service = FirebaseService()
    app.gemini_service = GeminiService()
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')
    app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
    
    # Web interface routes
    @app.route('/')
    def index():
        return render_template('chat.html')
    
    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')
    
    # Health check for Flutter
    @app.route('/api/health')
    def health_check():
        return jsonify({"status": "healthy", "message": "API is running"})
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
```

## models/user.py
```python
from datetime import datetime
from typing import Dict, List, Optional

class User:
    def __init__(self, uid: str, email: str, display_name: str = None):
        self.uid = uid
        self.email = email
        self.display_name = display_name
        self.created_at = datetime.utcnow()
        self.preferences = {
            "timezone": "UTC",
            "notification_preferences": {
                "email": True,
                "push": True,
                "reminder_advance": 15  # minutes
            }
        }
    
    def to_dict(self) -> Dict:
        return {
            "uid": self.uid,
            "email": self.email,
            "display_name": self.display_name,
            "created_at": self.created_at.isoformat(),
            "preferences": self.preferences
        }
    
    @classmethod
    def from_dict(cls, data: Dict):
        user = cls(data["uid"], data["email"], data.get("display_name"))
        user.created_at = datetime.fromisoformat(data["created_at"])
        user.preferences = data.get("preferences", user.preferences)
        return user
```

## models/task.py
```python
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

class TaskStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class Task:
    def __init__(self, title: str, description: str, user_id: str, 
                 due_date: datetime = None, priority: TaskPriority = TaskPriority.MEDIUM):
        self.id = None  # Will be set by Firebase
        self.title = title
        self.description = description
        self.user_id = user_id
        self.due_date = due_date
        self.priority = priority
        self.status = TaskStatus.PENDING
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.ai_generated = True
        self.conversation_id = None
        self.reminders = []
        self.subtasks = []
        
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "user_id": self.user_id,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "ai_generated": self.ai_generated,
            "conversation_id": self.conversation_id,
            "reminders": [r.to_dict() for r in self.reminders],
            "subtasks": [s.to_dict() for s in self.subtasks]
        }
    
    @classmethod
    def from_dict(cls, data: Dict):
        task = cls(
            data["title"], 
            data["description"], 
            data["user_id"],
            datetime.fromisoformat(data["due_date"]) if data["due_date"] else None,
            TaskPriority(data["priority"])
        )
        task.id = data.get("id")
        task.status = TaskStatus(data["status"])
        task.created_at = datetime.fromisoformat(data["created_at"])
        task.updated_at = datetime.fromisoformat(data["updated_at"])
        task.ai_generated = data.get("ai_generated", True)
        task.conversation_id = data.get("conversation_id")
        return task

class Reminder:
    def __init__(self, task_id: str, reminder_time: datetime, message: str):
        self.id = None
        self.task_id = task_id
        self.reminder_time = reminder_time
        self.message = message
        self.sent = False
        self.created_at = datetime.utcnow()
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "reminder_time": self.reminder_time.isoformat(),
            "message": self.message,
            "sent": self.sent,
            "created_at": self.created_at.isoformat()
        }
```

## models/conversation.py
```python
from datetime import datetime
from typing import Dict, List

class ConversationMessage:
    def __init__(self, content: str, role: str, timestamp: datetime = None):
        self.content = content
        self.role = role  # 'user' or 'assistant'
        self.timestamp = timestamp or datetime.utcnow()
    
    def to_dict(self) -> Dict:
        return {
            "content": self.content,
            "role": self.role,
            "timestamp": self.timestamp.isoformat()
        }

class Conversation:
    def __init__(self, user_id: str):
        self.id = None
        self.user_id = user_id
        self.messages: List[ConversationMessage] = []
        self.context = {
            "user_preferences": {},
            "current_tasks": [],
            "past_conversations": [],
            "user_schedule": {}
        }
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def add_message(self, content: str, role: str):
        message = ConversationMessage(content, role)
        self.messages.append(message)
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "messages": [msg.to_dict() for msg in self.messages],
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
```

## services/firebase_service.py
```python
import firebase_admin
from firebase_admin import credentials, firestore, auth
import pyrebase
from config import Config
from typing import Dict, List, Optional
import json

class FirebaseService:
    def __init__(self):
        # Initialize Firebase Admin SDK
        if not firebase_admin._apps:
            cred = credentials.Certificate("firebase_config.json")
            firebase_admin.initialize_app(cred)
        
        self.db = firestore.client()
        
        # Initialize Pyrebase for client operations
        self.firebase_client = pyrebase.initialize_app(Config.FIREBASE_CONFIG)
        self.auth_client = self.firebase_client.auth()
    
    # User Management
    def create_user(self, email: str, password: str, display_name: str = None) -> Dict:
        try:
            user = auth.create_user(
                email=email,
                password=password,
                display_name=display_name
            )
            
            # Store user data in Firestore
            user_data = {
                "uid": user.uid,
                "email": email,
                "display_name": display_name,
                "created_at": firestore.SERVER_TIMESTAMP
            }
            self.db.collection('users').document(user.uid).set(user_data)
            
            return {"success": True, "uid": user.uid}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def verify_id_token(self, id_token: str) -> Optional[Dict]:
        try:
            decoded_token = auth.verify_id_token(id_token)
            return decoded_token
        except Exception as e:
            return None
    
    # Task Management
    def save_task(self, task: Dict) -> str:
        doc_ref = self.db.collection('tasks').add(task)
        return doc_ref[1].id
    
    def get_user_tasks(self, user_id: str, status: str = None) -> List[Dict]:
        query = self.db.collection('tasks').where('user_id', '==', user_id)
        if status:
            query = query.where('status', '==', status)
        
        tasks = []
        for doc in query.stream():
            task_data = doc.to_dict()
            task_data['id'] = doc.id
            tasks.append(task_data)
        return tasks
    
    def update_task(self, task_id: str, updates: Dict):
        self.db.collection('tasks').document(task_id).update(updates)
    
    def delete_task(self, task_id: str):
        self.db.collection('tasks').document(task_id).delete()
    
    # Conversation Management
    def save_conversation(self, conversation: Dict) -> str:
        doc_ref = self.db.collection('conversations').add(conversation)
        return doc_ref[1].id
    
    def get_user_conversations(self, user_id: str, limit: int = 10) -> List[Dict]:
        conversations = []
        docs = (self.db.collection('conversations')
                .where('user_id', '==', user_id)
                .order_by('updated_at', direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream())
        
        for doc in docs:
            conv_data = doc.to_dict()
            conv_data['id'] = doc.id
            conversations.append(conv_data)
        return conversations
    
    def update_conversation(self, conversation_id: str, updates: Dict):
        self.db.collection('conversations').document(conversation_id).update(updates)
    
    # User Context Management
    def get_user_context(self, user_id: str) -> Dict:
        # Get recent tasks
        recent_tasks = self.get_user_tasks(user_id)
        
        # Get conversation history
        conversations = self.get_user_conversations(user_id, limit=5)
        
        # Get user preferences
        user_doc = self.db.collection('users').document(user_id).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        
        return {
            "recent_tasks": recent_tasks,
            "conversation_history": conversations,
            "user_preferences": user_data.get("preferences", {}),
            "user_profile": user_data
        }
```

## services/gemini_service.py
```python
import google.generativeai as genai
from config import Config
from prompts.gemini_prompts import TASK_CREATION_PROMPT, TASK_REFINEMENT_PROMPT, CONTEXT_ANALYSIS_PROMPT
from typing import Dict, List, Optional
import json
import re
from datetime import datetime, timedelta

class GeminiService:
    def __init__(self):
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
    def generate_tasks_from_message(self, user_message: str, user_context: Dict) -> Dict:
        """Generate tasks and reminders from user message with context"""
        try:
            prompt = self._build_task_creation_prompt(user_message, user_context)
            
            response = self.model.generate_content(prompt)
            
            # Parse the structured response
            return self._parse_gemini_response(response.text)
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Gemini API error: {str(e)}",
                "tasks": [],
                "suggestions": []
            }
    
    def refine_tasks(self, original_tasks: List[Dict], user_feedback: str, user_context: Dict) -> Dict:
        """Refine tasks based on user feedback"""
        try:
            prompt = self._build_task_refinement_prompt(original_tasks, user_feedback, user_context)
            
            response = self.model.generate_content(prompt)
            
            return self._parse_gemini_response(response.text)
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Gemini API error: {str(e)}",
                "tasks": [],
                "suggestions": []
            }
    
    def analyze_context_for_suggestions(self, user_context: Dict) -> Dict:
        """Analyze user context to provide proactive suggestions"""
        try:
            prompt = self._build_context_analysis_prompt(user_context)
            
            response = self.model.generate_content(prompt)
            
            return self._parse_gemini_response(response.text)
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Context analysis error: {str(e)}",
                "suggestions": []
            }
    
    def _build_task_creation_prompt(self, user_message: str, user_context: Dict) -> str:
        """Build the task creation prompt with context"""
        context_summary = self._summarize_context(user_context)
        
        return TASK_CREATION_PROMPT.format(
            user_message=user_message,
            context_summary=context_summary,
            current_date=datetime.now().strftime("%Y-%m-%d"),
            current_time=datetime.now().strftime("%H:%M")
        )
    
    def _build_task_refinement_prompt(self, original_tasks: List[Dict], user_feedback: str, user_context: Dict) -> str:
        """Build the task refinement prompt"""
        context_summary = self._summarize_context(user_context)
        tasks_json = json.dumps(original_tasks, indent=2)
        
        return TASK_REFINEMENT_PROMPT.format(
            original_tasks=tasks_json,
            user_feedback=user_feedback,
            context_summary=context_summary,
            current_date=datetime.now().strftime("%Y-%m-%d")
        )
    
    def _build_context_analysis_prompt(self, user_context: Dict) -> str:
        """Build the context analysis prompt"""
        context_summary = self._summarize_context(user_context)
        
        return CONTEXT_ANALYSIS_PROMPT.format(
            context_summary=context_summary,
            current_date=datetime.now().strftime("%Y-%m-%d"),
            current_time=datetime.now().strftime("%H:%M")
        )
    
    def _summarize_context(self, user_context: Dict) -> str:
        """Summarize user context for prompts"""
        summary_parts = []
        
        # Recent tasks summary
        recent_tasks = user_context.get("recent_tasks", [])
        if recent_tasks:
            task_summaries = [f"- {task.get('title', '')}: {task.get('status', '')}" for task in recent_tasks[:5]]
            summary_parts.append(f"Recent Tasks:\n" + "\n".join(task_summaries))
        
        # Conversation history summary
        conversations = user_context.get("conversation_history", [])
        if conversations:
            summary_parts.append(f"Recent conversation topics: {len(conversations)} conversations")
        
        # User preferences
        preferences = user_context.get("user_preferences", {})
        if preferences:
            summary_parts.append(f"User preferences: {json.dumps(preferences)}")
        
        return "\n\n".join(summary_parts) if summary_parts else "No previous context available."
    
    def _parse_gemini_response(self, response_text: str) -> Dict:
        """Parse structured response from Gemini"""
        try:
            # Look for JSON block in the response
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                return json.loads(json_str)
            
            # Fallback: try to parse the entire response as JSON
            return json.loads(response_text)
            
        except json.JSONDecodeError:
            # If JSON parsing fails, return a basic structure
            return {
                "success": True,
                "tasks": [],
                "suggestions": [response_text],
                "raw_response": response_text
            }
```

## prompts/gemini_prompts.py
```python
TASK_CREATION_PROMPT = """
You are an AI task scheduler and productivity assistant. Your role is to help users organize their thoughts, plans, and ideas into actionable tasks with appropriate reminders.

Current Context:
- Date: {current_date}
- Time: {current_time}
- User's Previous Context: {context_summary}

User Message: "{user_message}"

Based on the user's message and their context, create a structured task plan. Consider:

1. **Task Analysis**: Break down the user's message into specific, actionable tasks
2. **Priority Assessment**: Determine the urgency and importance of each task
3. **Time Estimation**: Estimate how long each task might take
4. **Dependencies**: Identify if tasks depend on each other
5. **Reminders**: Create appropriate reminders based on deadlines and importance
6. **Context Awareness**: Consider the user's previous tasks and preferences

Guidelines:
- Create realistic, achievable tasks
- Include both main tasks and subtasks when appropriate
- Set reminders that give adequate preparation time
- Consider the user's schedule and existing commitments
- Provide alternative suggestions if the original plan might be too ambitious
- Be specific about dates and times when possible

Return your response in the following JSON format:

```json
{{
  "success": true,
  "analysis": {{
    "user_intent": "Brief description of what the user wants to accomplish",
    "key_priorities": ["Priority 1", "Priority 2", "Priority 3"],
    "time_frame": "Estimated time frame for completion",
    "complexity_assessment": "Simple/Medium/Complex"
  }},
  "tasks": [
    {{
      "title": "Task title",
      "description": "Detailed description of what needs to be done",
      "priority": "low|medium|high|urgent",
      "estimated_duration": "Duration in minutes",
      "due_date": "YYYY-MM-DD HH:MM or null",
      "category": "work|personal|health|learning|social|other",
      "subtasks": [
        {{
          "title": "Subtask title",
          "description": "Subtask description",
          "estimated_duration": "Duration in minutes"
        }}
      ],
      "reminders": [
        {{
          "reminder_time": "YYYY-MM-DD HH:MM",
          "message": "Reminder message",
          "type": "deadline|preparation|follow_up"
        }}
      ],
      "prerequisites": ["Any dependencies or requirements"],
      "resources_needed": ["Tools, materials, or information needed"]
    }}
  ],
  "suggestions": [
    {{
      "type": "optimization|alternative|additional",
      "title": "Suggestion title",
      "description": "Detailed suggestion",
      "reasoning": "Why this suggestion might be helpful"
    }}
  ],
  "next_steps": [
    "Immediate next action the user should take",
    "Second priority action",
    "Third priority action"
  ]
}}
```

Make sure to:
- Be specific and actionable in task descriptions
- Consider realistic time estimates
- Create meaningful reminders that add value
- Provide thoughtful suggestions for improvement
- Maintain context awareness from previous interactions
"""

TASK_REFINEMENT_PROMPT = """
You are refining a task plan based on user feedback. The user has reviewed the original tasks and provided feedback.

Current Context:
- Date: {current_date}
- User's Context: {context_summary}

Original Tasks:
{original_tasks}

User Feedback: "{user_feedback}"

Based on the user's feedback, refine the task plan. Consider:

1. **Feedback Analysis**: Understand what the user liked and didn't like
2. **Adjustments**: Modify tasks according to their preferences
3. **Alternative Approaches**: Offer different ways to accomplish the same goals
4. **Improved Scheduling**: Better timing based on their concerns
5. **Complexity Adjustment**: Make tasks simpler or more detailed as needed

Guidelines:
- Address all points raised in the user's feedback
- Maintain the core objectives while adjusting the approach
- Offer multiple alternatives when possible
- Keep successful elements from the original plan
- Explain changes and reasoning

Return your response in the same JSON format as the task creation prompt, but include an additional "changes_made" section explaining what was modified and why.

```json
{{
  "success": true,
  "changes_made": {{
    "summary": "Brief overview of changes made",
    "specific_adjustments": [
      {{
        "change": "Description of change",
        "reasoning": "Why this change was made",
        "addresses_feedback": "How this addresses user feedback"
      }}
    ]
  }},
  "analysis": {{
    // Same structure as before
  }},
  "tasks": [
    // Refined tasks with same structure
  ],
  "suggestions": [
    // Updated suggestions
  ],
  "alternatives": [
    {{
      "title": "Alternative approach title",
      "description": "Different way to accomplish the goals",
      "pros": ["Advantage 1", "Advantage 2"],
      "cons": ["Disadvantage 1", "Disadvantage 2"]
    }}
  ]
}}
```
"""

CONTEXT_ANALYSIS_PROMPT = """
You are analyzing a user's context to provide proactive suggestions and insights.

Current Context:
- Date: {current_date}
- Time: {current_time}
- User's Context: {context_summary}

Based on the user's recent activity, tasks, and patterns, provide:

1. **Pattern Analysis**: Identify patterns in their task completion and planning
2. **Productivity Insights**: Observations about their productivity habits
3. **Proactive Suggestions**: Tasks or reminders they might benefit from
4. **Optimization Opportunities**: Ways to improve their workflow
5. **Potential Issues**: Things they might have forgotten or overlooked

Guidelines:
- Be helpful but not overwhelming
- Focus on actionable insights
- Consider their work-life balance
- Identify potential scheduling conflicts
- Suggest improvements based on their history

Return your response in JSON format:

```json
{{
  "success": true,
  "insights": {{
    "productivity_patterns": [
      {{
        "pattern": "Description of observed pattern",
        "frequency": "How often this occurs",
        "impact": "positive|negative|neutral"
      }}
    ],
    "completion_rate": {{
      "percentage": "Estimated task completion rate",
      "trend": "improving|declining|stable",
      "factors": ["Factor 1", "Factor 2"]
    }},
    "time_management": {{
      "strengths": ["Strength 1", "Strength 2"],
      "areas_for_improvement": ["Area 1", "Area 2"]
    }}
  }},
  "suggestions": [
    {{
      "type": "task|reminder|habit|optimization",
      "priority": "low|medium|high",
      "title": "Suggestion title",
      "description": "Detailed suggestion",
      "reasoning": "Why this would be beneficial",
      "implementation": "How to implement this suggestion"
    }}
  ],
  "potential_issues": [
    {{
      "issue": "Description of potential issue",
      "severity": "low|medium|high",
      "recommendation": "How to address this issue"
    }}
  ],
  "achievements": [
    {{
      "achievement": "Something the user did well",
      "impact": "Positive impact of this achievement"
    }}
  ]
}}
```
"""

CONVERSATION_CONTEXT_PROMPT = """
You are maintaining conversation context for a task scheduling AI. Your role is to:

1. Remember what the user has discussed
2. Track their goals and progress
3. Maintain continuity across conversations
4. Identify recurring themes and preferences

Current conversation: {current_messages}
Previous context: {previous_context}

Update the conversation context and identify key information that should be preserved for future interactions.

Return a JSON response with updated context information.
"""
```

## routes/auth.py
```python
from flask import Blueprint, request, jsonify, current_app
from services.firebase_service import FirebaseService
from models.user import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        display_name = data.get('display_name')
        
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400
        
        firebase_service = current_app.firebase_service
        result = firebase_service.create_user(email, password, display_name)
        
        if result["success"]:
            return jsonify({
                "message": "User created successfully",
                "uid": result["uid"]
            }), 201
        else:
            return jsonify({"error": result["error"]}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route('/verify', methods=['POST'])
def verify_token():
    try:
        data = request.get_json()
        id_token = data.get('id_token')
        
        if not id_token:
            return jsonify({"error": "ID token is required"}), 400
        
        firebase_service = current_app.firebase_service
        decoded_token = firebase_service.verify_id_token(id_token)
        
        if decoded_token:
            return jsonify({
                "valid": True,
                "uid": decoded_token["uid"],
                "email": decoded_token.get("email")
            })
        else:
            return jsonify({"valid": False}), 401
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route('/profile/<user_id>', methods=['GET'])
def get_profile(user_id):
    try:
        firebase_service = current_app.firebase_service
        context = firebase_service.get_user_context(user_id)
        
        return jsonify({
            "profile": context.get("user_profile", {}),
            "preferences": context.get("user_preferences", {}),
            "stats": {
                "total_tasks": len(context.get("recent_tasks", [])),
                "completed_tasks": len([t for t in context.get("recent_tasks", []) if t.get("status") == "completed"]),
                "conversations": len(context.get("conversation_history", []))
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

## routes/chat.py
```python
from flask import Blueprint, request, jsonify, current_app
from services.firebase_service import FirebaseService
from services.gemini_service import GeminiService
from models.conversation import Conversation
from datetime import datetime

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/send', methods=['POST'])
def send_message():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        message = data.get('message')
        conversation_id = data.get('conversation_id')
        
        if not user_id or not message:
            return jsonify({"error": "user_id and message are required"}), 400
        
        firebase_service = current_app.firebase_service
        gemini_service = current_app.gemini_service
        
        # Get user context
        user_context = firebase_service.get_user_context(user_id)
        
        # Get or create conversation
        if conversation_id:
            # Load existing conversation
            conversations = firebase_service.get_user_conversations(user_id)
            conversation_data = next((c for c in conversations if c['id'] == conversation_id), None)
            if not conversation_data:
                return jsonify({"error": "Conversation not found"}), 404
        else:
            # Create new conversation
            conversation = Conversation(user_id)
            conversation_data = conversation.to_dict()
            conversation_id = firebase_service.save_conversation(conversation_data)
            conversation_data['id'] = conversation_id
        
        # Add user message to conversation
        conversation_data['messages'].append({
            "content": message,
            "role": "user",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Generate AI response
        ai_response = gemini_service.generate_tasks_from_message(message, user_context)
        
        # Add AI response to conversation
        conversation_data['messages'].append({
            "content": ai_response,
            "role": "assistant",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Update conversation in Firebase
        firebase_service.update_conversation(conversation_id, {
            "messages": conversation_data['messages'],
            "updated_at": datetime.utcnow()
        })
        
        return jsonify({
            "conversation_id": conversation_id,
            "response": ai_response,
            "message_count": len(conversation_data['messages'])
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/conversations/<user_id>', methods=['GET'])
def get_conversations(user_id):
    try:
        firebase_service = current_app.firebase_service
        conversations = firebase_service.get_user_conversations(user_id)
        
        return jsonify({"conversations": conversations})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/conversation/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    try:
        firebase_service = current_app.firebase_service
        # This would need to be implemented in firebase_service
        # For now, return a placeholder
        return jsonify({"conversation": {}})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/refine', methods=['POST'])
def refine_tasks():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        original_tasks = data.get('original_tasks')
        feedback = data.get('feedback')
        conversation_id = data.get('conversation_id')
        
        if not all([user_id, original_tasks, feedback]):
            return jsonify({"error": "user_id, original_tasks, and feedback are required"}), 400
        
        firebase_service = current_app.firebase_service
        gemini_service = current_app.gemini_service
        
        # Get user context
        user_context = firebase_service.get_user_context(user_id)
        
        # Generate refined tasks
        refined_response = gemini_service.refine_tasks(original_tasks, feedback, user_context)
        
        # Update conversation if provided
        if conversation_id:
            firebase_service.update_conversation(conversation_id, {
                "messages": firebase_service.db.collection('conversations').document(conversation_id).get().to_dict()['messages'] + [
                    {
                        "content": feedback,
                        "role": "user",
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    {
                        "content": refined_response,
                        "role": "assistant",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                ],
                "updated_at": datetime.utcnow()
            })
        
        return jsonify({
            "refined_tasks": refined_response,
            "conversation_id": conversation_id
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

## routes/tasks.py
```python
from flask import Blueprint, request, jsonify, current_app
from services.firebase_service import FirebaseService
from models.task import Task, TaskStatus, TaskPriority
from datetime import datetime

tasks_bp = Blueprint('tasks', __name__)

@tasks_bp.route('/create', methods=['POST'])
def create_tasks():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        tasks_data = data.get('tasks')
        conversation_id = data.get('conversation_id')
        
        if not user_id or not tasks_data:
            return jsonify({"error": "user_id and tasks are required"}), 400
        
        firebase_service = current_app.firebase_service
        created_tasks = []
        
        for task_data in tasks_data:
            # Create task object
            task = Task(
                title=task_data.get('title'),
                description=task_data.get('description'),
                user_id=user_id,
                due_date=datetime.fromisoformat(task_data['due_date']) if task_data.get('due_date') else None,
                priority=TaskPriority(task_data.get('priority', 'medium'))
            )
            task.conversation_id = conversation_id
            
            # Save to Firebase
            task_dict = task.to_dict()
            task_id = firebase_service.save_task(task_dict)
            task_dict['id'] = task_id
            created_tasks.append(task_dict)
        
        return jsonify({
            "created_tasks": created_tasks,
            "count": len(created_tasks)
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/user/<user_id>', methods=['GET'])
def get_user_tasks(user_id):
    try:
        status = request.args.get('status')
        limit = int(request.args.get('limit', 50))
        
        firebase_service = current_app.firebase_service
        tasks = firebase_service.get_user_tasks(user_id, status)
        
        # Limit results
        tasks = tasks[:limit]
        
        return jsonify({
            "tasks": tasks,
            "count": len(tasks)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/<task_id>', methods=['PUT'])
def update_task(task_id):
    try:
        data = request.get_json()
        
        # Prepare updates
        updates = {}
        if 'status' in data:
            updates['status'] = data['status']
        if 'title' in data:
            updates['title'] = data['title']
        if 'description' in data:
            updates['description'] = data['description']
        if 'due_date' in data:
            updates['due_date'] = data['due_date']
        if 'priority' in data:
            updates['priority'] = data['priority']
        
        updates['updated_at'] = datetime.utcnow().isoformat()
        
        firebase_service = current_app.firebase_service
        firebase_service.update_task(task_id, updates)
        
        return jsonify({"message": "Task updated successfully"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    try:
        firebase_service = current_app.firebase_service
        firebase_service.delete_task(task_id)
        
        return jsonify({"message": "Task deleted successfully"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/approve', methods=['POST'])
def approve_tasks():
    try:
        data = request.get_json()
        task_ids = data.get('task_ids', [])
        user_id = data.get('user_id')
        
        if not task_ids or not user_id:
            return jsonify({"error": "task_ids and user_id are required"}), 400
        
        firebase_service = current_app.firebase_service
        
        for task_id in task_ids:
            firebase_service.update_task(task_id, {
                'status': TaskStatus.APPROVED.value,
                'updated_at': datetime.utcnow().isoformat()
            })
        
        return jsonify({
            "message": f"Approved {len(task_ids)} tasks",
            "approved_tasks": task_ids
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/stats/<user_id>', methods=['GET'])
def get_task_stats(user_id):
    try:
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        
        stats = {
            "total": len(all_tasks),
            "pending": len([t for t in all_tasks if t.get('status') == 'pending']),
            "approved": len([t for t in all_tasks if t.get('status') == 'approved']),
            "completed": len([t for t in all_tasks if t.get('status') == 'completed']),
            "cancelled": len([t for t in all_tasks if t.get('status') == 'cancelled']),
            "by_priority": {
                "urgent": len([t for t in all_tasks if t.get('priority') == 'urgent']),
                "high": len([t for t in all_tasks if t.get('priority') == 'high']),
                "medium": len([t for t in all_tasks if t.get('priority') == 'medium']),
                "low": len([t for t in all_tasks if t.get('priority') == 'low'])
            }
        }
        
        return jsonify({"stats": stats})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

## templates/base.html
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Task Scheduler</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .chat-container {
            height: calc(100vh - 2rem);
        }
        .message-bubble {
            max-width: 80%;
            word-wrap: break-word;
        }
    </style>
</head>
<body class="bg-gray-100">
    {% block content %}{% endblock %}
    
    <script>
        // Global JavaScript functions for the web interface
        async function sendMessage(message, userId) {
            try {
                const response = await fetch('/api/chat/send', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        user_id: userId,
                        message: message
                    })
                });
                
                return await response.json();
            } catch (error) {
                console.error('Error sending message:', error);
                return { error: 'Failed to send message' };
            }
        }
        
        async function approveTasks(taskIds, userId) {
            try {
                const response = await fetch('/api/tasks/approve', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        task_ids: taskIds,
                        user_id: userId
                    })
                });
                
                return await response.json();
            } catch (error) {
                console.error('Error approving tasks:', error);
                return { error: 'Failed to approve tasks' };
            }
        }
    </script>
</body>
</html>
```

## templates/chat.html
```html
{% extends "base.html" %}

{% block content %}
<div class="container mx-auto p-4 chat-container">
    <div class="bg-white rounded-lg shadow-lg h-full flex flex-col">
        <!-- Header -->
        <div class="bg-blue-600 text-white p-4 rounded-t-lg">
            <h1 class="text-xl font-bold">AI Task Scheduler</h1>
            <p class="text-blue-100">Tell me what you want to accomplish, and I'll help you organize it!</p>
        </div>
        
        <!-- Chat Messages -->
        <div id="chatMessages" class="flex-1 p-4 overflow-y-auto space-y-4">
            <div class="message-bubble bg-gray-200 p-3 rounded-lg">
                <p class="text-gray-800">👋 Hello! I'm your AI task scheduler. Tell me what you're planning to do, and I'll help you organize it into actionable tasks with reminders.</p>
            </div>
        </div>
        
        <!-- Input Area -->
        <div class="p-4 border-t">
            <div class="flex space-x-2">
                <input 
                    type="text" 
                    id="messageInput" 
                    placeholder="Tell me what you want to accomplish..."
                    class="flex-1 p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    onkeypress="handleKeyPress(event)"
                >
                <button 
                    onclick="sendUserMessage()"
                    class="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                    Send
                </button>
            </div>
        </div>
    </div>
</div>

<script>
    let currentUserId = 'demo-user-' + Math.random().toString(36).substr(2, 9);
    let currentConversationId = null;
    
    function handleKeyPress(event) {
        if (event.key === 'Enter') {
            sendUserMessage();
        }
    }
    
    async function sendUserMessage() {
        const input = document.getElementById('messageInput');
        const message = input.value.trim();
        
        if (!message) return;
        
        // Add user message to chat
        addMessageToChat(message, 'user');
        input.value = '';
        
        // Add loading indicator
        const loadingId = addLoadingMessage();
        
        try {
            const response = await sendMessage(message, currentUserId);
            
            // Remove loading indicator
            removeLoadingMessage(loadingId);
            
            if (response.error) {
                addMessageToChat('Sorry, I encountered an error: ' + response.error, 'assistant');
                return;
            }
            
            currentConversationId = response.conversation_id;
            
            // Display AI response
            displayAIResponse(response.response);
            
        } catch (error) {
            removeLoadingMessage(loadingId);
            addMessageToChat('Sorry, I encountered an error. Please try again.', 'assistant');
        }
    }
    
    function addMessageToChat(message, role) {
        const chatMessages = document.getElementById('chatMessages');
        const messageDiv = document.createElement('div');
        
        if (role === 'user') {
            messageDiv.className = 'message-bubble bg-blue-600 text-white p-3 rounded-lg ml-auto';
        } else {
            messageDiv.className = 'message-bubble bg-gray-200 p-3 rounded-lg';
        }
        
        messageDiv.innerHTML = `<p>${message}</p>`;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        return messageDiv;
    }
    
    function addLoadingMessage() {
        const chatMessages = document.getElementById('chatMessages');
        const loadingDiv = document.createElement('div');
        const loadingId = 'loading-' + Date.now();
        
        loadingDiv.id = loadingId;
        loadingDiv.className = 'message-bubble bg-gray-200 p-3 rounded-lg';
        loadingDiv.innerHTML = '<p>🤔 Thinking...</p>';
        
        chatMessages.appendChild(loadingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        return loadingId;
    }
    
    function removeLoadingMessage(loadingId) {
        const loadingDiv = document.getElementById(loadingId);
        if (loadingDiv) {
            loadingDiv.remove();
        }
    }
    
    function displayAIResponse(response) {
        const chatMessages = document.getElementById('chatMessages');
        const responseDiv = document.createElement('div');
        responseDiv.className = 'message-bubble bg-gray-200 p-3 rounded-lg';
        
        if (response.success && response.tasks && response.tasks.length > 0) {
            let html = '<div class="space-y-3">';
            html += '<p class="font-semibold text-gray-800">I\'ve created a plan for you:</p>';
            
            // Display tasks
            response.tasks.forEach((task, index) => {
                html += `
                    <div class="border border-gray-300 p-3 rounded-lg bg-white">
                        <h4 class="font-semibold text-gray-800">${task.title}</h4>
                        <p class="text-gray-600 text-sm mt-1">${task.description}</p>
                        <div class="flex items-center mt-2 space-x-4 text-xs text-gray-500">
                            <span class="bg-${getPriorityColor(task.priority)}-100 text-${getPriorityColor(task.priority)}-800 px-2 py-1 rounded">
                                ${task.priority} priority
                            </span>
                            ${task.due_date ? `<span>📅 ${formatDate(task.due_date)}</span>` : ''}
                            ${task.estimated_duration ? `<span>⏱️ ${task.estimated_duration} min</span>` : ''}
                        </div>
                    </div>
                `;
            });
            
            // Add approval buttons
            html += `
                <div class="flex space-x-2 mt-4">
                    <button 
                        onclick="approveAllTasks(${JSON.stringify(response.tasks).replace(/"/g, '&quot;')})"
                        class="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 text-sm"
                    >
                        ✅ Approve All
                    </button>
                    <button 
                        onclick="provideFeedback()"
                        class="bg-yellow-600 text-white px-4 py-2 rounded hover:bg-yellow-700 text-sm"
                    >
                        🔄 Suggest Changes
                    </button>
                </div>
            `;
            
            html += '</div>';
            responseDiv.innerHTML = html;
        } else {
            // Display raw response or suggestions
            responseDiv.innerHTML = `<p>${response.raw_response || 'I understand what you want to do, but I need more details to create specific tasks.'}</p>`;
        }
        
        chatMessages.appendChild(responseDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    function getPriorityColor(priority) {
        const colors = {
            'urgent': 'red',
            'high': 'orange',
            'medium': 'blue',
            'low': 'gray'
        };
        return colors[priority] || 'gray';
    }
    
    function formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    }
    
    async function approveAllTasks(tasks) {
        try {
            // Create tasks in database
            const createResponse = await fetch('/api/tasks/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: currentUserId,
                    tasks: tasks,
                    conversation_id: currentConversationId
                })
            });
            
            const result = await createResponse.json();
            
            if (result.error) {
                addMessageToChat('Error creating tasks: ' + result.error, 'assistant');
                return;
            }
            
            // Approve the created tasks
            const taskIds = result.created_tasks.map(t => t.id);
            const approveResponse = await approveTasks(taskIds, currentUserId);
            
            if (approveResponse.error) {
                addMessageToChat('Tasks created but approval failed: ' + approveResponse.error, 'assistant');
                return;
            }
            
            addMessageToChat(`✅ Perfect! I've created and approved ${result.count} tasks for you. You can view them in your dashboard.`, 'assistant');
            
        } catch (error) {
            addMessageToChat('Sorry, there was an error creating your tasks. Please try again.', 'assistant');
        }
    }
    
    function provideFeedback() {
        const feedback = prompt("What would you like me to change about these tasks?");
        if (feedback) {
            addMessageToChat(feedback, 'user');
            // Here you would call the refine endpoint
            addMessageToChat("I'll refine the tasks based on your feedback...", 'assistant');
        }
    }
</script>
{% endblock %}
```

## API Endpoints Summary

### Authentication Endpoints
- `POST /api/auth/register` - Register new user
- `POST /api/auth/verify` - Verify Firebase ID token
- `GET /api/auth/profile/<user_id>` - Get user profile

### Chat Endpoints
- `POST /api/chat/send` - Send message and get AI response
- `GET /api/chat/conversations/<user_id>` - Get user's conversations
- `GET /api/chat/conversation/<conversation_id>` - Get specific conversation
- `POST /api/chat/refine` - Refine tasks based on feedback

### Task Endpoints
- `POST /api/tasks/create` - Create new tasks
- `GET /api/tasks/user/<user_id>` - Get user's tasks
- `PUT /api/tasks/<task_id>` - Update task
- `DELETE /api/tasks/<task_id>` - Delete task
- `POST /api/tasks/approve` - Approve multiple tasks
- `GET /api/tasks/stats/<user_id>` - Get task statistics

### Health Check
- `GET /api/health` - API health check

## Firebase Configuration

Create `firebase_config.json` with your Firebase service account credentials:

```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "your-private-key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-...@your-project.iam.gserviceaccount.com",
  "client_id": "your-client-id",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-...%40your-project.iam.gserviceaccount.com"
}
```

## Running the Application

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up Firebase configuration file

3. Run the application:
   ```bash
   python app.py
   ```

4. Access the web interface at `http://localhost:5000`

## Flutter Integration Ready

This backend is designed to work seamlessly with Flutter apps:

- All endpoints return JSON responses
- CORS is configured for cross-origin requests
- Authentication uses Firebase tokens
- RESTful API design
- Comprehensive error handling
- Health check endpoint for monitoring

The API provides all necessary endpoints for a Flutter app to:
- Handle user authentication
- Send/receive chat messages
- Create and manage tasks
- Get user statistics and context
- Handle real-time updates (can be extended with WebSockets)

## Key Features

1. **AI-Powered Task Creation**: Uses Gemini AI to convert natural language into structured tasks
2. **Context Awareness**: Maintains conversation history and user context
3. **Task Refinement**: Allows users to provide feedback and get refined suggestions
4. **Firebase Integration**: Complete user management and data storage
5. **Flutter Ready**: RESTful API designed for mobile app integration
6. **Scalable Architecture**: Modular design with separate services and routes
7. **Comprehensive Task Management**: Full CRUD operations for tasks with priority and status tracking