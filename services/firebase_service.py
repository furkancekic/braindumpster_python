import firebase_admin
from firebase_admin import credentials, firestore, auth
import pyrebase
from config import Config
from typing import Dict, List, Optional
import json
import logging

class FirebaseService:
    def __init__(self):
        self.logger = logging.getLogger('braindumpster.firebase')
        self.logger.info("🔥 Initializing Firebase service...")
        # Initialize Firebase Admin SDK
        if not firebase_admin._apps:
            try:
                self.logger.info("📄 Loading Firebase credentials from firebase_config.json...")
                cred = credentials.Certificate("firebase_config.json")
                firebase_admin.initialize_app(cred)
                self.logger.info("✅ Firebase Admin SDK initialized successfully")
            except FileNotFoundError:
                self.logger.warning("⚠️ firebase_config.json not found. Using mock Firebase service.")
                self.logger.info("ℹ️ To enable Firebase, create firebase_config.json from firebase_config.json.example")
                # Initialize with default project for development
                firebase_admin.initialize_app()
                self.logger.info("🔧 Firebase Admin SDK initialized with default project")
        
        try:
            self.logger.info("🗄️ Initializing Firestore client...")
            self.db = firestore.client()
            self.logger.info("✅ Firestore client initialized successfully")
        except Exception as e:
            self.logger.error(f"❌ Could not initialize Firestore: {e}")
            self.db = None
        
        # Initialize Pyrebase for client operations
        try:
            self.logger.info("🔐 Initializing Pyrebase client...")
            self.firebase_client = pyrebase.initialize_app(Config.FIREBASE_CONFIG)
            self.auth_client = self.firebase_client.auth()
            self.logger.info("✅ Pyrebase client initialized successfully")
        except Exception as e:
            self.logger.error(f"❌ Could not initialize Pyrebase: {e}")
            self.firebase_client = None
            self.auth_client = None
    
    # User Management
    def create_user(self, email: str, password: str, display_name: str = None, timezone: str = 'UTC') -> Dict:
        self.logger.info(f"👤 Creating new user: {email}")
        self.logger.debug(f"📝 Display name: {display_name}")
        self.logger.debug(f"🌍 Timezone: {timezone}")
        
        if not self.db:
            self.logger.error("❌ Firebase not configured - cannot create user")
            return {"success": False, "error": "Firebase not configured"}
        
        try:
            self.logger.info("🔐 Creating Firebase Auth user...")
            user = auth.create_user(
                email=email,
                password=password,
                display_name=display_name
            )
            self.logger.info(f"✅ Firebase Auth user created with UID: {user.uid}")
            
            # Store user data in Firestore with timezone preferences
            user_data = {
                "uid": user.uid,
                "email": email,
                "display_name": display_name,
                "created_at": firestore.SERVER_TIMESTAMP,
                "preferences": {
                    "timezone": timezone,
                    "notification_preferences": {
                        "email": True,
                        "push": True,
                        "reminder_advance": 15  # minutes
                    }
                }
            }
            self.logger.info("🗄️ Storing user data in Firestore...")
            self.db.collection('users').document(user.uid).set(user_data)
            self.logger.info(f"✅ User data stored successfully for UID: {user.uid} with timezone: {timezone}")
            
            return {"success": True, "uid": user.uid}
        except Exception as e:
            self.logger.error(f"❌ Error creating user: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def verify_id_token(self, id_token: str) -> Optional[Dict]:
        self.logger.info("🔐 Verifying ID token...")
        self.logger.debug(f"🎫 Token (first 50 chars): {id_token[:50]}...")
        
        if not self.db:
            self.logger.error("❌ Firebase not configured - cannot verify token")
            return None
        try:
            decoded_token = auth.verify_id_token(id_token)
            self.logger.info(f"✅ Token verified successfully for UID: {decoded_token.get('uid')}")
            return decoded_token
        except Exception as e:
            self.logger.error(f"❌ Token verification failed: {str(e)}")
            return None
    
    # Task Management
    def save_tasks_batch(self, tasks: List[Dict]) -> List[str]:
        """Save multiple tasks in a batch operation for better performance"""
        self.logger.info(f"💾 Saving {len(tasks)} tasks in batch mode")
        
        if not self.db:
            # Return mock IDs for development
            import time
            mock_ids = [f"mock_task_{int(time.time())}_{i}" for i in range(len(tasks))]
            self.logger.warning(f"⚠️ Firebase not configured - returning {len(mock_ids)} mock IDs")
            return mock_ids
        
        # Ensure connection is healthy
        self._ensure_connection()
        
        try:
            batch = self.db.batch()
            task_refs = []
            
            for task in tasks:
                # Create a new document reference
                doc_ref = self.db.collection('tasks').document()
                batch.set(doc_ref, task)
                task_refs.append(doc_ref)
                self.logger.debug(f"📝 Prepared task for batch: {task.get('title', 'Unknown')}")
            
            # Commit the batch
            self.logger.info("🗄️ Committing batch to Firestore...")
            batch.commit()
            
            # Extract IDs
            task_ids = [ref.id for ref in task_refs]
            self.logger.info(f"✅ Batch saved successfully: {len(task_ids)} tasks")
            return task_ids
            
        except Exception as e:
            self.logger.error(f"❌ Error saving batch: {str(e)}")
            raise
    
    def save_task(self, task: Dict) -> str:
        self.logger.info(f"💾 Saving task: {task.get('title', 'Unknown')}")
        self.logger.debug(f"📋 Task data: {json.dumps(task, indent=2, default=str)}")
        self.logger.info(f"👤 Task user_id: {task.get('user_id', 'NO_USER_ID')}")
        
        if not self.db:
            # Return mock ID for development
            import time
            mock_id = f"mock_task_{int(time.time())}"
            self.logger.warning(f"⚠️ Firebase not configured - returning mock ID: {mock_id}")
            return mock_id
        
        try:
            self.logger.info("🗄️ Adding task to Firestore...")
            doc_ref = self.db.collection('tasks').add(task)
            task_id = doc_ref[1].id
            self.logger.info(f"✅ Task saved successfully with ID: {task_id}")
            return task_id
        except Exception as e:
            self.logger.error(f"❌ Error saving task: {str(e)}")
            raise
    
    def get_user_tasks(self, user_id: str, status = None, 
                       include_past_due: bool = True, 
                       include_past_reminders: bool = True, 
                       filter_by_date: str = None) -> List[Dict]:
        self.logger.info(f"📋 Getting tasks for user: {user_id}")
        self.logger.debug(f"🔍 Status filter: {status}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning empty task list")
            return []
        
        try:
            # Build efficient server-side query
            self.logger.info(f"🗄️ Querying tasks for user {user_id} from Firestore...")
            
            # Start with user_id filter (most selective)
            query = self.db.collection('tasks').where('user_id', '==', user_id)
            
            # Add status filter if specified
            if status is not None:
                if isinstance(status, list):
                    # For multiple statuses, use 'in' operator
                    query = query.where('status', 'in', status)
                    self.logger.debug(f"🔍 Added status filter for multiple values: {status}")
                else:
                    # Single status
                    query = query.where('status', '==', status)
                    self.logger.debug(f"🔍 Added status filter: {status}")
            
            # Execute the query
            docs = query.stream()
            
            tasks = []
            for doc in docs:
                task_data = doc.to_dict()
                task_data['id'] = doc.id

                # Filter out archived tasks (soft deleted after 30 days)
                if task_data.get('archived', False):
                    self.logger.debug(f"🗄️ Filtering out archived task: {task_data.get('title', 'Unknown')}")
                    continue

                # Filter out deleted tasks unless specifically requested
                if status is None or (isinstance(status, list) and 'deleted' not in status) or (isinstance(status, str) and status != 'deleted'):
                    if task_data.get('status') == 'deleted':
                        self.logger.debug(f"🗑️ Filtering out deleted task: {task_data.get('title', 'Unknown')}")
                        continue

                tasks.append(task_data)
                self.logger.debug(f"✅ Task {doc.id}: {task_data.get('title', 'Unknown')}")
            
            self.logger.info(f"🎯 Query complete: Retrieved {len(tasks)} tasks for user {user_id} (after filtering deleted)")
            
            # Apply time-based filtering if requested
            if not include_past_due or not include_past_reminders or filter_by_date:
                tasks = self._apply_time_filters(tasks, include_past_due, include_past_reminders, filter_by_date)
            
            # Format all timestamps to absolute format
            tasks = self._format_task_timestamps(tasks)
            
            self.logger.info(f"📤 Returning {len(tasks)} filtered and formatted tasks")
            return tasks
        except Exception as e:
            self.logger.error(f"❌ Error querying tasks: {e}")
            return []
    
    def _apply_time_filters(self, tasks: List[Dict], include_past_due: bool, 
                           include_past_reminders: bool, filter_by_date: str) -> List[Dict]:
        """Apply time-based filtering to tasks"""
        from datetime import datetime, date, timezone
        
        filtered_tasks = []
        now = datetime.now(timezone.utc)
        today = date.today()
        
        self.logger.debug(f"🕐 Applying time filters: past_due={include_past_due}, past_reminders={include_past_reminders}, date_filter={filter_by_date}")
        
        for task in tasks:
            should_include = True
            
            # Filter past due dates
            if not include_past_due and task.get('due_date'):
                try:
                    # Handle both string and Firestore timestamp formats
                    due_date_str = task['due_date']
                    if hasattr(due_date_str, 'strftime'):  # Firestore timestamp
                        # Convert Firestore timestamp to timezone-aware datetime
                        if hasattr(due_date_str, 'astimezone'):
                            due_date = due_date_str.astimezone(timezone.utc)
                        else:
                            # Fallback: assume it's naive and add UTC timezone
                            due_date = due_date_str.replace(tzinfo=timezone.utc)
                    else:  # String format
                        due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                    
                    if due_date.date() < today:
                        self.logger.debug(f"🗓️ Excluding past due task: {task.get('title')} (due: {due_date.date()})")
                        should_include = False
                        continue
                except Exception as e:
                    self.logger.warning(f"⚠️ Error parsing due_date for task {task.get('id')}: {e}")
            
            # Filter today's tasks only if specified
            if filter_by_date == 'today' and task.get('due_date'):
                try:
                    due_date_str = task['due_date']
                    if hasattr(due_date_str, 'strftime'):  # Firestore timestamp
                        # Convert Firestore timestamp to timezone-aware datetime
                        if hasattr(due_date_str, 'astimezone'):
                            due_date = due_date_str.astimezone(timezone.utc)
                        else:
                            # Fallback: assume it's naive and add UTC timezone
                            due_date = due_date_str.replace(tzinfo=timezone.utc)
                    else:  # String format
                        due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                    
                    if due_date.date() != today:
                        self.logger.debug(f"📅 Excluding non-today task: {task.get('title')} (due: {due_date.date()})")
                        should_include = False
                        continue
                except Exception as e:
                    self.logger.warning(f"⚠️ Error parsing due_date for today filter: {e}")
            
            # Filter past reminder times
            if not include_past_reminders and task.get('reminders'):
                active_reminders = []
                for reminder in task['reminders']:
                    try:
                        reminder_time_str = reminder.get('reminder_time')
                        if reminder_time_str:
                            if hasattr(reminder_time_str, 'strftime'):  # Firestore timestamp
                                # Convert Firestore timestamp to timezone-aware datetime
                                if hasattr(reminder_time_str, 'astimezone'):
                                    reminder_time = reminder_time_str.astimezone(timezone.utc)
                                else:
                                    # Fallback: assume it's naive and add UTC timezone
                                    reminder_time = reminder_time_str.replace(tzinfo=timezone.utc)
                            else:  # String format
                                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                            
                            # Include if reminder is in future AND not sent yet
                            if reminder_time > now and not reminder.get('sent', False):
                                active_reminders.append(reminder)
                            else:
                                self.logger.debug(f"⏰ Excluding past reminder: {reminder_time} (sent: {reminder.get('sent', False)})")
                    except Exception as e:
                        self.logger.warning(f"⚠️ Error parsing reminder_time: {e}")
                        # Keep reminder if parsing fails
                        active_reminders.append(reminder)
                
                task['reminders'] = active_reminders
                
                # If task has no active reminders and no due_date, exclude from today's plan
                if filter_by_date == 'today' and not active_reminders and not task.get('due_date'):
                    self.logger.debug(f"📋 Excluding task with no active reminders: {task.get('title')}")
                    should_include = False
                    continue
            
            if should_include:
                filtered_tasks.append(task)
        
        self.logger.info(f"🔽 Time filtering: {len(tasks)} → {len(filtered_tasks)} tasks")
        return filtered_tasks
    
    def _format_task_timestamps(self, tasks: List[Dict]) -> List[Dict]:
        """Format all timestamps to absolute format (YYYY-MM-DD HH:MM)"""
        from datetime import datetime, timezone
        
        for task in tasks:
            # Format due_date
            if task.get('due_date'):
                try:
                    due_date_str = task['due_date']
                    if hasattr(due_date_str, 'strftime'):  # Firestore timestamp
                        # Convert Firestore timestamp to timezone-aware datetime
                        if hasattr(due_date_str, 'astimezone'):
                            due_date = due_date_str.astimezone(timezone.utc)
                        else:
                            # Fallback: assume it's naive and add UTC timezone
                            due_date = due_date_str.replace(tzinfo=timezone.utc)
                    else:  # String format
                        due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                    
                    # Format to YYYY-MM-DD HH:MM
                    task['due_date_formatted'] = due_date.strftime('%Y-%m-%d %H:%M')
                    task['due_date_display'] = due_date.strftime('%d %b %H:%M')  # 10 Jul 15:30
                except Exception as e:
                    self.logger.warning(f"⚠️ Error formatting due_date: {e}")
            
            # Format reminder times
            if task.get('reminders'):
                for reminder in task['reminders']:
                    try:
                        reminder_time_str = reminder.get('reminder_time')
                        if reminder_time_str:
                            if hasattr(reminder_time_str, 'strftime'):  # Firestore timestamp
                                # Convert Firestore timestamp to timezone-aware datetime
                                if hasattr(reminder_time_str, 'astimezone'):
                                    reminder_time = reminder_time_str.astimezone(timezone.utc)
                                else:
                                    # Fallback: assume it's naive and add UTC timezone
                                    reminder_time = reminder_time_str.replace(tzinfo=timezone.utc)
                            else:  # String format
                                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                            
                            # Add formatted timestamps
                            reminder['reminder_time_formatted'] = reminder_time.strftime('%Y-%m-%d %H:%M')
                            reminder['reminder_time_display'] = reminder_time.strftime('%d %b %H:%M')  # 10 Jul 15:30
                    except Exception as e:
                        self.logger.warning(f"⚠️ Error formatting reminder_time: {e}")
            
            # Format created_at and updated_at if they exist
            for field in ['created_at', 'updated_at']:
                if task.get(field):
                    try:
                        timestamp = task[field]
                        if hasattr(timestamp, 'strftime'):  # Firestore timestamp
                            # Convert Firestore timestamp to timezone-aware datetime
                            if hasattr(timestamp, 'astimezone'):
                                dt = timestamp.astimezone(timezone.utc)
                            else:
                                # Fallback: assume it's naive and add UTC timezone
                                dt = timestamp.replace(tzinfo=timezone.utc)
                        else:  # String format
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        
                        task[f'{field}_formatted'] = dt.strftime('%Y-%m-%d %H:%M')
                        task[f'{field}_display'] = dt.strftime('%d %b %H:%M')
                    except Exception as e:
                        self.logger.warning(f"⚠️ Error formatting {field}: {e}")
        
        return tasks
    
    def get_task(self, task_id: str, user_id: str = None) -> Dict:
        """Get a single task by ID with optional user verification"""
        self.logger.info(f"📄 Getting task: {task_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning empty task")
            return {}
        
        try:
            task_doc = self.db.collection('tasks').document(task_id).get()
            
            if not task_doc.exists:
                self.logger.warning(f"❌ Task {task_id} not found")
                return {}
            
            task_data = task_doc.to_dict()
            task_data['id'] = task_doc.id
            
            # Security: If user_id is provided, verify ownership
            if user_id and task_data.get('user_id') != user_id:
                self.logger.warning(f"❌ User {user_id} attempted to access task {task_id} owned by {task_data.get('user_id')}")
                return {}
            
            self.logger.info(f"✅ Retrieved task: {task_data.get('title', 'Unknown')}")
            return task_data
            
        except Exception as e:
            self.logger.error(f"❌ Error getting task {task_id}: {e}")
            return {}
    
    def update_task(self, task_id: str, updates: Dict):
        self.logger.info(f"📝 Updating task: {task_id}")
        self.logger.debug(f"🔄 Updates: {json.dumps(updates, indent=2, default=str)}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot update task")
            return
        
        try:
            self.db.collection('tasks').document(task_id).update(updates)
            self.logger.info(f"✅ Task {task_id} updated successfully")
        except Exception as e:
            self.logger.error(f"❌ Error updating task {task_id}: {str(e)}")
            raise
    
    def delete_task(self, task_id: str):
        self.logger.info(f"🗑️ Deleting task: {task_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot delete task")
            return
        
        try:
            self.db.collection('tasks').document(task_id).delete()
            self.logger.info(f"✅ Task {task_id} deleted successfully")
        except Exception as e:
            self.logger.error(f"❌ Error deleting task {task_id}: {str(e)}")
            raise
    
    # Conversation Management
    def save_conversation(self, conversation: Dict) -> str:
        self.logger.info(f"💬 Saving conversation for user: {conversation.get('user_id', 'Unknown')}")
        self.logger.debug(f"📋 Conversation data: {json.dumps(conversation, indent=2, default=str)}")
        
        if not self.db:
            import time
            mock_id = f"mock_conv_{int(time.time())}"
            self.logger.warning(f"⚠️ Firebase not configured - returning mock conversation ID: {mock_id}")
            return mock_id
        
        try:
            doc_ref = self.db.collection('conversations').add(conversation)
            conv_id = doc_ref[1].id
            self.logger.info(f"✅ Conversation saved successfully with ID: {conv_id}")
            return conv_id
        except Exception as e:
            self.logger.error(f"❌ Error saving conversation: {str(e)}")
            raise
    
    def get_user_conversations(self, user_id: str, limit: int = 10) -> List[Dict]:
        self.logger.info(f"💬 Getting conversations for user: {user_id} (limit: {limit})")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning empty conversation list")
            return []
        
        try:
            # Build efficient server-side query
            self.logger.info(f"🗄️ Querying conversations for user {user_id} from Firestore...")
            
            # Query with user_id filter, order by updated_at, and limit
            query = (self.db.collection('conversations')
                    .where('user_id', '==', user_id)
                    .order_by('updated_at', direction='DESCENDING')
                    .limit(limit))
            
            docs = query.stream()
            
            conversations = []
            for doc in docs:
                conv_data = doc.to_dict()
                conv_data['id'] = doc.id
                conversations.append(conv_data)
            
            self.logger.info(f"🎯 Query complete: Returning {len(conversations)} conversations for user {user_id}")
            
            return conversations
        except Exception as e:
            self.logger.error(f"❌ Error querying conversations: {e}")
            return []
    
    def update_conversation(self, conversation_id: str, updates: Dict):
        self.logger.info(f"📝 Updating conversation: {conversation_id}")
        self.logger.debug(f"🔄 Updates: {json.dumps(updates, indent=2, default=str)}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot update conversation")
            return
        
        try:
            self.db.collection('conversations').document(conversation_id).update(updates)
            self.logger.info(f"✅ Conversation {conversation_id} updated successfully")
        except Exception as e:
            self.logger.error(f"❌ Error updating conversation {conversation_id}: {str(e)}")
            raise
    
    # User Context Management
    def get_user_context(self, user_id: str) -> Dict:
        self.logger.info(f"🔍 Getting complete user context for: {user_id}")
        
        # Ensure connection is healthy
        self._ensure_connection()
        
        # Get recent tasks
        self.logger.info("📋 Fetching user tasks...")
        recent_tasks = self.get_user_tasks(user_id)
        self.logger.info(f"✅ Found {len(recent_tasks)} tasks for user")
        
        # Debug: Log task details for duplicate detection
        if recent_tasks:
            self.logger.debug("🔍 DEBUG: Tasks found for context:")
            for task in recent_tasks[:5]:  # Log first 5 tasks
                self.logger.debug(f"  - ID: {task.get('id')}, Title: {task.get('title')}, Status: {task.get('status')}")
        else:
            self.logger.warning("⚠️ DEBUG: No tasks found for context - duplicate detection may not work")
        
        # Get conversation history
        self.logger.info("💬 Fetching conversation history...")
        conversations = self.get_user_conversations(user_id, limit=5)
        self.logger.info(f"✅ Found {len(conversations)} conversations for user")
        
        # Get user preferences
        self.logger.info("👤 Fetching user profile and preferences...")
        if self.db:
            try:
                user_doc = self.db.collection('users').document(user_id).get()
                user_data = user_doc.to_dict() if user_doc.exists else {}
                self.logger.info(f"✅ User profile loaded: {user_data.get('display_name', 'No name')}")
            except Exception as e:
                self.logger.error(f"❌ Error fetching user profile: {str(e)}")
                user_data = {}
        else:
            self.logger.warning("⚠️ Firebase not configured - using empty user data")
            user_data = {}
        
        context = {
            "recent_tasks": recent_tasks,
            "conversation_history": conversations,
            "user_preferences": user_data.get("preferences", {}),
            "user_profile": user_data
        }
        
        self.logger.info(f"🎯 Complete user context assembled: {len(recent_tasks)} tasks, {len(conversations)} conversations")
        self.logger.debug(f"📊 Context summary: tasks={len(recent_tasks)}, conversations={len(conversations)}, preferences={len(user_data.get('preferences', {}))}")
        
        return context
    
    def get_conversation_by_id(self, conversation_id: str) -> Optional[Dict]:
        """Get a specific conversation by ID"""
        self.logger.info(f"🔍 Getting conversation by ID: {conversation_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot get conversation")
            return None
        
        try:
            doc = self.db.collection('conversations').document(conversation_id).get()
            if doc.exists:
                conversation = doc.to_dict()
                conversation['id'] = doc.id
                self.logger.info(f"✅ Conversation {conversation_id} found")
                return conversation
            else:
                self.logger.warning(f"⚠️ Conversation {conversation_id} not found")
                return None
        except Exception as e:
            self.logger.error(f"❌ Error getting conversation {conversation_id}: {str(e)}")
            return None
    
    def delete_conversation(self, conversation_id: str):
        """Delete a conversation by ID"""
        self.logger.info(f"🗑️ Deleting conversation: {conversation_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot delete conversation")
            return
        
        try:
            self.db.collection('conversations').document(conversation_id).delete()
            self.logger.info(f"✅ Conversation {conversation_id} deleted successfully")
        except Exception as e:
            self.logger.error(f"❌ Error deleting conversation {conversation_id}: {str(e)}")
            raise
    
    def search_user_conversations(self, user_id: str, query: str) -> List[Dict]:
        """Search conversations by query string"""
        self.logger.info(f"🔍 Searching conversations for user {user_id} with query: '{query}'")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning empty search results")
            return []
        
        try:
            # Get all user conversations first
            conversations = self.get_user_conversations(user_id, limit=100)
            
            # Filter by query in title or messages
            filtered_conversations = []
            query_lower = query.lower()
            
            for conv in conversations:
                # Search in title
                if query_lower in conv.get('title', '').lower():
                    filtered_conversations.append(conv)
                    continue
                
                # Search in messages
                messages = conv.get('messages', [])
                for message in messages:
                    if query_lower in str(message.get('content', '')).lower():
                        filtered_conversations.append(conv)
                        break
            
            self.logger.info(f"✅ Found {len(filtered_conversations)} conversations matching query")
            return filtered_conversations
            
        except Exception as e:
            self.logger.error(f"❌ Error searching conversations: {str(e)}")
            return []
    
    def get_conversation_stats(self, user_id: str) -> Dict:
        """Get conversation statistics for a user"""
        self.logger.info(f"📊 Getting conversation stats for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning empty stats")
            return {}
        
        try:
            conversations = self.get_user_conversations(user_id, limit=1000)
            
            total_conversations = len(conversations)
            total_messages = 0
            
            for conv in conversations:
                messages = conv.get('messages', [])
                total_messages += len(messages)
            
            stats = {
                'total_conversations': total_conversations,
                'total_messages': total_messages,
                'average_messages_per_conversation': total_messages / total_conversations if total_conversations > 0 else 0
            }
            
            self.logger.info(f"✅ Conversation stats calculated: {stats}")
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Error getting conversation stats: {str(e)}")
            return {}
    
    # Notification and Token Management
    def get_user_tokens(self, user_id: str) -> List[str]:
        """Get FCM device tokens for a user"""
        self.logger.info(f"📱 Getting FCM tokens for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning empty token list")
            return []
        
        try:
            user_doc = self.db.collection('users').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                tokens = user_data.get('fcm_tokens', [])
                self.logger.info(f"✅ Found {len(tokens)} FCM tokens for user")
                return tokens
            else:
                self.logger.warning(f"⚠️ User document not found: {user_id}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error getting user tokens: {str(e)}")
            return []
    
    def update_user_tokens(self, user_id: str, tokens: List[str]) -> bool:
        """Update FCM device tokens for a user"""
        self.logger.info(f"📱 Updating FCM tokens for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - skipping token update")
            return False
        
        try:
            user_ref = self.db.collection('users').document(user_id)

            # Check if document exists, if not create it
            user_doc = user_ref.get()
            if not user_doc.exists:
                self.logger.info(f"🆕 Creating new user document for FCM tokens: {user_id}")
                user_ref.set({
                    'user_id': user_id,
                    'fcm_tokens': tokens,
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            else:
                # Document exists, update it
                user_ref.update({
                    'fcm_tokens': tokens,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })

            self.logger.info(f"✅ Updated FCM tokens for user: {len(tokens)} tokens")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error updating user tokens: {str(e)}")
            return False
    
    def get_all_users(self, limit: int = None, offset: int = 0) -> List[Dict]:
        """Get all users for batch operations with optional pagination"""
        self.logger.info("👥 Getting all users")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning empty user list")
            return []
        
        try:
            query = self.db.collection('users')
            
            # Add pagination if specified
            if limit is not None:
                query = query.limit(limit)
                if offset > 0:
                    # For offset, we need to use a cursor-based approach
                    # This is a simplified version - in production, use proper cursor pagination
                    self.logger.warning(f"⚠️ Offset pagination not fully implemented - fetching first {limit} users only")
            
            docs = query.stream()
            
            users = []
            for doc in docs:
                user_data = doc.to_dict()
                user_data['id'] = doc.id
                users.append(user_data)
            
            self.logger.info(f"✅ Retrieved {len(users)} users")
            return users
            
        except Exception as e:
            self.logger.error(f"❌ Error getting all users: {str(e)}")
            return []
    
    def get_due_reminders(self, user_id: str, current_time, user_timezone: str = None) -> List[Dict]:
        """Get due reminders for a user"""
        from datetime import datetime, timezone
        import pytz
        
        self.logger.info(f"⏰ Getting due reminders for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning empty reminder list")
            return []
        
        try:
            # Use provided timezone or get user's timezone preference
            if not user_timezone:
                user_timezone = self._get_user_timezone(user_id)
            self.logger.debug(f"🌍 User timezone: {user_timezone}")
            
            # Get user's active tasks (approved or pending)
            tasks = self.get_user_tasks(user_id, status=['approved', 'pending'])
            
            due_reminders = []
            
            for task in tasks:
                reminders = task.get('reminders', [])
                for reminder in reminders:
                    # Check if reminder is due and not sent
                    reminder_time_str = reminder.get('reminder_time')
                    if not reminder_time_str or reminder.get('sent', False):
                        continue
                    
                    try:
                        # Parse reminder time
                        # CRITICAL FIX: Set check_if_past=False to allow due (past) reminders!
                        if isinstance(reminder_time_str, str):
                            reminder_time = self._parse_reminder_time(reminder_time_str, user_timezone, check_if_past=False)
                            if reminder_time is None:
                                continue
                        else:
                            continue
                        
                        # Ensure current_time is timezone-aware for comparison
                        comparison_time = current_time
                        if comparison_time.tzinfo is None:
                            comparison_time = comparison_time.replace(tzinfo=timezone.utc)
                        
                        # Check if due
                        if reminder_time <= comparison_time:
                            # Generate ID for reminder if it doesn't have one (for existing reminders)
                            reminder_id = reminder.get('id')
                            if not reminder_id:
                                import uuid
                                reminder_id = str(uuid.uuid4())
                                # Update the reminder with the new ID
                                reminder['id'] = reminder_id
                                self.logger.debug(f"🆔 Generated missing ID for reminder: {reminder_id}")
                            
                            due_reminders.append({
                                'task_id': task['id'],
                                'reminder_id': reminder_id,
                                'reminder_time': reminder_time,
                                'message': reminder.get('message', ''),
                                'task_title': task.get('title', ''),
                                'task_priority': task.get('priority', 'medium')
                            })
                    except Exception as e:
                        self.logger.error(f"❌ Error parsing reminder time: {e}")
                        continue
            
            self.logger.info(f"✅ Found {len(due_reminders)} due reminders")
            return due_reminders
            
        except Exception as e:
            self.logger.error(f"❌ Error getting due reminders: {str(e)}")
            return []
    
    def _get_user_timezone(self, user_id: str) -> str:
        """Get user's timezone preference, default to UTC"""
        try:
            user_doc = self.db.collection('users').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                preferences = user_data.get('preferences', {})
                return preferences.get('timezone', 'UTC')
        except Exception as e:
            self.logger.warning(f"⚠️ Error getting user timezone: {e}")
        return 'UTC'
    
    def _parse_reminder_time(self, reminder_time_str, user_timezone: str, check_if_past: bool = True):
        """Parse reminder time string with proper timezone handling

        Args:
            reminder_time_str: The reminder time to parse
            user_timezone: User's timezone for naive datetime conversion
            check_if_past: If True, returns None for past reminders. Set to False when checking due reminders.
        """
        from datetime import datetime, timezone
        import pytz

        try:
            reminder_time = None  # Initialize

            # Handle DatetimeWithNanoseconds or other datetime objects
            if not isinstance(reminder_time_str, str):
                # If it's already a datetime object
                if isinstance(reminder_time_str, datetime):
                    reminder_time = reminder_time_str
                    # Ensure it has timezone info
                    if reminder_time.tzinfo is None:
                        # Use user's timezone for naive datetime objects
                        user_tz = pytz.timezone(user_timezone)
                        reminder_time = user_tz.localize(reminder_time)
                        reminder_time = reminder_time.astimezone(timezone.utc)
                    elif reminder_time.tzinfo != timezone.utc:
                        reminder_time = reminder_time.astimezone(timezone.utc)
                    self.logger.debug(f"🕒 Parsed datetime object to UTC: {reminder_time}")
                elif hasattr(reminder_time_str, 'isoformat'):
                    # Convert datetime object to string
                    reminder_time_str = reminder_time_str.isoformat()
                else:
                    # Convert to string as fallback
                    reminder_time_str = str(reminder_time_str)

            # Parse from string if not already parsed as datetime object
            if reminder_time is None and isinstance(reminder_time_str, str):
                # First try to parse as ISO format with timezone
                if 'Z' in reminder_time_str or '+' in reminder_time_str or ('-' in reminder_time_str and 'T' in reminder_time_str):
                    # Already has timezone info
                    reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                    # Ensure it's actually timezone-aware
                    if reminder_time.tzinfo is None:
                        self.logger.warning(f"⚠️ String looked timezone-aware but parsed as naive: {reminder_time_str}")
                        reminder_time = reminder_time.replace(tzinfo=timezone.utc)
                    elif reminder_time.tzinfo != timezone.utc:
                        reminder_time = reminder_time.astimezone(timezone.utc)
                    self.logger.debug(f"🕒 Parsed timezone-aware reminder to UTC: {reminder_time}")
                else:
                    # Parse as naive datetime
                    reminder_time = datetime.fromisoformat(reminder_time_str)

                    # Handle timezone-naive datetime
                    if reminder_time.tzinfo is None:
                        try:
                            # Use user's timezone for naive datetimes
                            user_tz = pytz.timezone(user_timezone)
                            reminder_time = user_tz.localize(reminder_time)
                            self.logger.debug(f"🌍 Assumed naive reminder time is user's timezone ({user_timezone}): {reminder_time}")
                            # Convert to UTC for consistent storage and comparison
                            reminder_time = reminder_time.astimezone(timezone.utc)
                            self.logger.debug(f"🌍 Converted to UTC: {reminder_time}")
                        except Exception as tz_error:
                            self.logger.warning(f"⚠️ Error with user timezone conversion: {tz_error}")
                            # Fallback to UTC
                            reminder_time = reminder_time.replace(tzinfo=timezone.utc)
                            self.logger.debug(f"🕒 Fallback: converted naive reminder time to UTC: {reminder_time}")
                    else:
                        # It has timezone, convert to UTC
                        reminder_time = reminder_time.astimezone(timezone.utc)
                        self.logger.debug(f"🌍 Converted timezone-aware to UTC: {reminder_time}")

            # CRITICAL: Check if reminder time is in the past (when creating reminders)
            # This prevents Gemini from creating past reminders
            # IMPORTANT: Only skip past reminders when check_if_past=True (during creation)
            # When checking due reminders (check_if_past=False), we MUST allow past times!
            if check_if_past:
                current_time_utc = datetime.now(timezone.utc)
                if reminder_time < current_time_utc:
                    time_diff = (current_time_utc - reminder_time).total_seconds() / 60
                    self.logger.warning(f"⚠️ Skipping PAST reminder during creation: {reminder_time.strftime('%Y-%m-%d %H:%M:%S %Z')} (was {time_diff:.1f} minutes ago)")
                    return None

            return reminder_time

        except Exception as e:
            self.logger.error(f"❌ Error parsing reminder time '{reminder_time_str}': {e}")
            import traceback
            self.logger.error(f"   Traceback: {traceback.format_exc()}")
            return None
    
    def mark_reminder_as_sent(self, task_id: str, reminder_id: str) -> bool:
        """Mark a specific reminder as sent"""
        self.logger.info(f"✅ Marking reminder as sent: {task_id}/{reminder_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - skipping reminder update")
            return False
        
        try:
            # Get task document
            task_ref = self.db.collection('tasks').document(task_id)
            task_doc = task_ref.get()
            
            if not task_doc.exists:
                self.logger.error(f"❌ Task not found: {task_id}")
                return False
            
            task_data = task_doc.to_dict()
            reminders = task_data.get('reminders', [])
            
            # Update the specific reminder
            updated = False
            for reminder in reminders:
                if reminder.get('id') == reminder_id:
                    reminder['sent'] = True
                    updated = True
                    break
            
            if updated:
                task_ref.update({
                    'reminders': reminders,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
                self.logger.info(f"✅ Reminder marked as sent successfully")
                return True
            else:
                self.logger.error(f"❌ Reminder not found: {reminder_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error marking reminder as sent: {str(e)}")
            return False
    
    def get_user_daily_stats(self, user_id: str) -> Dict:
        """Get daily task statistics for a user"""
        from datetime import datetime, date
        
        self.logger.info(f"📊 Getting daily stats for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning empty stats")
            return {}
        
        try:
            tasks = self.get_user_tasks(user_id)
            today = date.today()
            
            pending_tasks = 0
            completed_tasks_today = 0
            
            for task in tasks:
                # Count pending tasks
                if task.get('status') in ['pending', 'approved']:
                    pending_tasks += 1
                
                # Count completed tasks from today
                if task.get('status') == 'completed':
                    updated_at = task.get('updated_at')
                    if updated_at:
                        try:
                            if hasattr(updated_at, 'date'):
                                task_date = updated_at.date()
                            else:
                                # Parse ISO string
                                task_datetime = datetime.fromisoformat(str(updated_at).replace('Z', '+00:00'))
                                task_date = task_datetime.date()
                            
                            if task_date == today:
                                completed_tasks_today += 1
                        except Exception as e:
                            self.logger.error(f"❌ Error parsing task date: {e}")
                            continue
            
            stats = {
                'pending_tasks': pending_tasks,
                'completed_tasks': completed_tasks_today,
                'date': today.isoformat()
            }
            
            self.logger.info(f"✅ Daily stats calculated: {stats}")
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Error getting daily stats: {str(e)}")
            return {}
    
    def get_old_completed_tasks(self, user_id: str, cutoff_date) -> List[Dict]:
        """Get completed tasks older than cutoff date"""
        self.logger.info(f"📅 Getting old completed tasks for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning empty task list")
            return []
        
        try:
            tasks = self.get_user_tasks(user_id, status=['completed'])
            old_tasks = []
            
            for task in tasks:
                updated_at = task.get('updated_at')
                if updated_at:
                    try:
                        if hasattr(updated_at, 'replace'):
                            task_datetime = updated_at.replace(tzinfo=None)
                        else:
                            # Parse ISO string
                            task_datetime = datetime.fromisoformat(str(updated_at).replace('Z', '+00:00')).replace(tzinfo=None)
                        
                        if task_datetime < cutoff_date:
                            old_tasks.append(task)
                    except Exception as e:
                        self.logger.error(f"❌ Error parsing task date: {e}")
                        continue
            
            self.logger.info(f"✅ Found {len(old_tasks)} old completed tasks")
            return old_tasks
            
        except Exception as e:
            self.logger.error(f"❌ Error getting old completed tasks: {str(e)}")
            return []
    
    def archive_task(self, task_id: str) -> bool:
        """Archive a task (soft delete)"""
        self.logger.info(f"🗄️ Archiving task: {task_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - skipping archive")
            return False
        
        try:
            task_ref = self.db.collection('tasks').document(task_id)
            task_ref.update({
                'archived': True,
                'archived_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            self.logger.info(f"✅ Task archived successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error archiving task: {str(e)}")
            return False
    
    def get_notification_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get notification history for a user"""
        self.logger.info(f"📱 Getting notification history for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning empty notification history")
            return []
        
        try:
            # Query notification history for the user
            query = (self.db.collection('notification_history')
                    .where('user_id', '==', user_id)
                    .order_by('timestamp', direction='DESCENDING')
                    .limit(limit))
            
            docs = query.stream()
            
            history = []
            for doc in docs:
                notification_data = doc.to_dict()
                notification_data['id'] = doc.id
                history.append(notification_data)
            
            self.logger.info(f"✅ Retrieved {len(history)} notification history items")
            return history
            
        except Exception as e:
            self.logger.error(f"❌ Error getting notification history: {str(e)}")
            return []
    
    def get_user_notification_preferences(self, user_id: str) -> Dict:
        """Get notification preferences for a user"""
        self.logger.info(f"⚙️ Getting notification preferences for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - returning default preferences")
            return self._get_default_notification_preferences()
        
        try:
            user_doc = self.db.collection('users').document(user_id).get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                preferences = user_data.get('notification_preferences', {})
                
                # Merge with defaults to ensure all keys are present
                default_prefs = self._get_default_notification_preferences()
                default_prefs.update(preferences)
                
                self.logger.info(f"✅ Retrieved notification preferences for user {user_id}")
                return default_prefs
            else:
                self.logger.info(f"ℹ️ User document not found, returning default preferences")
                return self._get_default_notification_preferences()
                
        except Exception as e:
            self.logger.error(f"❌ Error getting notification preferences: {str(e)}")
            return self._get_default_notification_preferences()
    
    def update_user_notification_preferences(self, user_id: str, preferences: Dict) -> bool:
        """Update notification preferences for a user"""
        self.logger.info(f"⚙️ Updating notification preferences for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot update preferences")
            return False
        
        try:
            user_ref = self.db.collection('users').document(user_id)
            
            # Update only the notification_preferences field
            user_ref.update({
                'notification_preferences': preferences,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            self.logger.info(f"✅ Notification preferences updated for user {user_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error updating notification preferences: {str(e)}")
            return False
    
    def _get_default_notification_preferences(self) -> Dict:
        """Get default notification preferences"""
        return {
            'task_reminders': True,
            'task_approvals': True,
            'task_completions': True,
            'daily_summaries': True,
            'quiet_hours': {
                'enabled': False,
                'start_time': '22:00',
                'end_time': '08:00'
            },
            'reminder_sound': True,
            'vibration': True,
            'priority_filtering': {
                'urgent': True,
                'high': True,
                'medium': True,
                'low': False
            }
        }

    def health_check(self) -> bool:
        """Check if database connection is healthy"""
        self.logger.debug("🏥 Performing database health check")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured")
            return False
        
        try:
            # Try to access a small collection to test connectivity
            test_ref = self.db.collection('health_check').limit(1)
            list(test_ref.stream())
            self.logger.debug("✅ Database health check passed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Database health check failed: {str(e)}")
            return False
    
    def reconnect_if_needed(self) -> bool:
        """Reconnect to Firebase if connection is unhealthy"""
        if self.health_check():
            return True
        
        self.logger.warning("🔄 Connection unhealthy, attempting to reconnect...")
        
        try:
            # Reinitialize Firestore client
            self.db = firestore.client()
            self.logger.info("✅ Firebase reconnected successfully")
            
            # Test the new connection
            if self.health_check():
                self.logger.info("✅ New Firebase connection is healthy")
                return True
            else:
                self.logger.error("❌ New Firebase connection is still unhealthy")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Failed to reconnect to Firebase: {str(e)}")
            return False
    
    def _ensure_connection(self):
        """Ensure Firebase connection is healthy before operations"""
        if not self.reconnect_if_needed():
            raise Exception("Firebase connection is unhealthy and reconnection failed")
    
    # Subscription Management
    def get_user_subscription(self, user_id: str) -> Optional[Dict]:
        """Get user's current subscription"""
        self.logger.info(f"📋 Getting subscription for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot get subscription")
            return None
        
        try:
            self._ensure_connection()
            
            subscription_ref = self.db.collection('subscriptions').document(user_id)
            subscription_doc = subscription_ref.get()
            
            if subscription_doc.exists:
                subscription_data = subscription_doc.to_dict()
                self.logger.info(f"✅ Found subscription for user {user_id}: {subscription_data.get('tier')}")
                return subscription_data
            else:
                self.logger.info(f"ℹ️ No subscription found for user {user_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Error getting subscription for user {user_id}: {str(e)}")
            return None
    
    def save_user_subscription(self, user_id: str, subscription_data: Dict) -> bool:
        """Save or update user's subscription"""
        self.logger.info(f"💾 Saving subscription for user: {user_id}")

        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot save subscription")
            return False

        try:
            self._ensure_connection()

            subscription_ref = self.db.collection('subscriptions').document(user_id)

            # CRITICAL FIX: Calculate is_active and status based on expiration_date
            from datetime import datetime, timedelta

            expiration_date_str = subscription_data.get('expiration_date')

            # Lifetime subscriptions (no expiration)
            if not expiration_date_str:
                subscription_data['is_active'] = True
                subscription_data['status'] = 'active'
                self.logger.info(f"  Lifetime subscription - setting is_active=True")
            else:
                # Parse and validate expiration date
                try:
                    # Handle different date formats
                    if isinstance(expiration_date_str, str):
                        expiration_str_clean = expiration_date_str.replace('+00:00', '').replace('Z', '')
                        expiration_date = datetime.fromisoformat(expiration_str_clean)
                    else:
                        expiration_date = expiration_date_str

                    now = datetime.utcnow()
                    is_active = now < expiration_date

                    subscription_data['is_active'] = is_active
                    subscription_data['status'] = 'active' if is_active else 'expired'

                    self.logger.info(f"  Expiration: {expiration_date.isoformat()}")
                    self.logger.info(f"  Current time: {now.isoformat()}")
                    self.logger.info(f"  Calculated is_active: {is_active}")

                except Exception as e:
                    self.logger.error(f"  Error parsing expiration date: {e}")
                    # If parsing fails, default to active if expiration is in future
                    subscription_data['is_active'] = True
                    subscription_data['status'] = 'active'

            # Add metadata
            subscription_data.update({
                'updated_at': firestore.SERVER_TIMESTAMP
            })

            subscription_ref.set(subscription_data, merge=True)

            self.logger.info(f"✅ Subscription saved for user {user_id} (is_active={subscription_data['is_active']})")
            return True

        except Exception as e:
            self.logger.error(f"❌ Error saving subscription for user {user_id}: {str(e)}")
            return False
    
    def delete_user_subscription(self, user_id: str) -> bool:
        """Delete user's subscription (for downgrades to free)"""
        self.logger.info(f"🗑️ Deleting subscription for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot delete subscription")
            return False
        
        try:
            self._ensure_connection()
            
            subscription_ref = self.db.collection('subscriptions').document(user_id)
            subscription_ref.delete()
            
            self.logger.info(f"✅ Subscription deleted for user {user_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error deleting subscription for user {user_id}: {str(e)}")
            return False
    
    def deactivate_user_subscription(self, user_id: str) -> bool:
        """Deactivate user's subscription (mark as inactive)"""
        self.logger.info(f"⏹️ Deactivating subscription for user: {user_id}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot deactivate subscription")
            return False
        
        try:
            self._ensure_connection()
            
            subscription_ref = self.db.collection('subscriptions').document(user_id)
            subscription_ref.update({
                'is_active': False,
                'status': 'cancelled',
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            self.logger.info(f"✅ Subscription deactivated for user {user_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error deactivating subscription for user {user_id}: {str(e)}")
            return False
    
    def log_analytics_event(self, event_name: str, event_data: Dict) -> bool:
        """Log analytics event to Firebase"""
        self.logger.info(f"📊 Logging analytics event: {event_name}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot log analytics")
            return False
        
        try:
            self._ensure_connection()
            
            # Add to analytics collection
            analytics_ref = self.db.collection('analytics')
            
            # Add metadata
            event_data.update({
                'event_name': event_name,
                'created_at': firestore.SERVER_TIMESTAMP
            })
            
            analytics_ref.add(event_data)
            
            self.logger.info(f"✅ Analytics event logged: {event_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error logging analytics event {event_name}: {str(e)}")
            return False
    
    def get_subscription_analytics(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Get subscription analytics data"""
        self.logger.info(f"📈 Getting subscription analytics from {start_date} to {end_date}")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot get analytics")
            return []
        
        try:
            self._ensure_connection()
            
            analytics_ref = self.db.collection('analytics')
            
            # Filter by subscription events
            query = analytics_ref.where('event_name', 'in', ['subscription_purchase', 'subscription_cancellation'])
            
            # Add date filters if provided
            if start_date:
                query = query.where('created_at', '>=', start_date)
            if end_date:
                query = query.where('created_at', '<=', end_date)
            
            docs = query.stream()
            analytics_data = [doc.to_dict() for doc in docs]
            
            self.logger.info(f"✅ Retrieved {len(analytics_data)} analytics records")
            return analytics_data
            
        except Exception as e:
            self.logger.error(f"❌ Error getting subscription analytics: {str(e)}")
            return []
    
    def get_active_subscribers_count(self) -> int:
        """Get count of active subscribers"""
        self.logger.info("📊 Getting active subscribers count")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot get subscriber count")
            return 0
        
        try:
            self._ensure_connection()
            
            # Count active subscriptions
            subscriptions_ref = self.db.collection('subscriptions')
            active_query = subscriptions_ref.where('is_active', '==', True)
            
            # Get count without loading all documents
            active_subscriptions = list(active_query.stream())
            count = len(active_subscriptions)
            
            self.logger.info(f"✅ Found {count} active subscribers")
            return count
            
        except Exception as e:
            self.logger.error(f"❌ Error getting active subscribers count: {str(e)}")
            return 0
    
    def cleanup_expired_subscriptions(self) -> int:
        """Clean up expired subscriptions"""
        self.logger.info("🧹 Cleaning up expired subscriptions")
        
        if not self.db:
            self.logger.warning("⚠️ Firebase not configured - cannot cleanup subscriptions")
            return 0
        
        try:
            self._ensure_connection()
            
            from datetime import datetime
            
            subscriptions_ref = self.db.collection('subscriptions')
            
            # Get all active subscriptions
            active_query = subscriptions_ref.where('is_active', '==', True)
            active_subscriptions = active_query.stream()
            
            updated_count = 0
            for subscription_doc in active_subscriptions:
                subscription_data = subscription_doc.to_dict()
                expiration_date_str = subscription_data.get('expiration_date')
                
                if expiration_date_str:
                    try:
                        expiration_date = datetime.fromisoformat(expiration_date_str.replace('Z', '+00:00'))
                        if expiration_date < datetime.utcnow():
                            # Mark as expired
                            subscription_doc.reference.update({
                                'is_active': False,
                                'status': 'expired',
                                'updated_at': firestore.SERVER_TIMESTAMP
                            })
                            updated_count += 1
                            self.logger.info(f"📋 Marked subscription as expired for user: {subscription_doc.id}")
                    except ValueError:
                        self.logger.warning(f"⚠️ Invalid expiration date format for user: {subscription_doc.id}")
            
            self.logger.info(f"✅ Cleaned up {updated_count} expired subscriptions")
            return updated_count
            
        except Exception as e:
            self.logger.error(f"❌ Error cleaning up expired subscriptions: {str(e)}")
            return 0
    def save_recording(self, recording_data):
        """Save a meeting/lecture recording"""
        try:
            doc_ref = self.db.collection("recordings").document()
            recording_data["id"] = doc_ref.id
            doc_ref.set(recording_data)
            self.logger.info(f"💾 Recording saved: {doc_ref.id}")
            return doc_ref.id
        except Exception as e:
            self.logger.error(f"Error saving recording: {str(e)}")
            raise

    def get_user_recordings(self, user_id, recording_type=None, limit=50):
        """Get all recordings for a user"""
        try:
            query = self.db.collection("recordings").where("userId", "==", user_id)
            
            if recording_type:
                query = query.where("type", "==", recording_type)
            
            query = query.order_by("createdAt", direction="DESCENDING").limit(limit)
            
            recordings = []
            for doc in query.stream():
                recording_data = doc.to_dict()
                recording_data["id"] = doc.id
                recordings.append(recording_data)
            
            return recordings
        except Exception as e:
            self.logger.error(f"Error getting recordings: {str(e)}")
            return []

    def get_recording(self, recording_id, user_id):
        """Get a single recording by ID"""
        try:
            doc_ref = self.db.collection("recordings").document(recording_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return None
            
            recording_data = doc.to_dict()
            
            # Verify ownership
            if recording_data.get("userId") != user_id:
                return None
            
            recording_data["id"] = doc.id
            return recording_data
        except Exception as e:
            self.logger.error(f"Error getting recording: {str(e)}")
            return None

    def update_recording(self, recording_id, updates):
        """Update a recording"""
        try:
            doc_ref = self.db.collection("recordings").document(recording_id)
            doc_ref.update(updates)
            self.logger.info(f"📝 Recording updated: {recording_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating recording: {str(e)}")
            raise

    def delete_recording(self, recording_id, user_id):
        """Delete a recording"""
        try:
            # Verify ownership first
            recording = self.get_recording(recording_id, user_id)
            if not recording:
                raise ValueError("Recording not found or access denied")

            self.db.collection("recordings").document(recording_id).delete()
            self.logger.info(f"🗑️ Recording deleted: {recording_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error deleting recording: {str(e)}")
            raise

