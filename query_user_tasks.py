#!/usr/bin/env python3
"""
Direct Firebase Firestore Query Script
Query all tasks and reminders for user "dGpDR3AMYxWwIORfJok5M8gdzuv1"

This script directly connects to Firebase Firestore and retrieves:
- All tasks (active, completed, deleted)
- All reminders associated with each task
- User information and preferences
- Task statistics
"""

import firebase_admin
from firebase_admin import credentials, firestore
import json
from datetime import datetime
import logging
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FirestoreTaskQueryService:
    def __init__(self):
        """Initialize Firebase connection using the existing configuration"""
        self.db = None
        self._init_firebase()

    def _init_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            if not firebase_admin._apps:
                logger.info("🔥 Initializing Firebase Admin SDK...")
                cred = credentials.Certificate("firebase_config.json")
                firebase_admin.initialize_app(cred)
                logger.info("✅ Firebase Admin SDK initialized successfully")

            self.db = firestore.client()
            logger.info("✅ Firestore client initialized successfully")

        except FileNotFoundError:
            logger.error("❌ firebase_config.json not found!")
            raise
        except Exception as e:
            logger.error(f"❌ Error initializing Firebase: {e}")
            raise

    def format_timestamp(self, timestamp) -> str:
        """Format timestamp for display"""
        if timestamp is None:
            return "N/A"

        try:
            if hasattr(timestamp, 'strftime'):
                # Firestore timestamp
                return timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')
            else:
                # String format
                dt = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
                return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        except Exception as e:
            logger.warning(f"⚠️ Error formatting timestamp {timestamp}: {e}")
            return str(timestamp)

    def get_user_info(self, user_id: str) -> Dict:
        """Get user information and preferences"""
        logger.info(f"👤 Fetching user information for: {user_id}")

        try:
            user_doc = self.db.collection('users').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                logger.info(f"✅ User found: {user_data.get('display_name', 'No name')}")
                return user_data
            else:
                logger.warning(f"⚠️ User document not found for: {user_id}")
                return {}
        except Exception as e:
            logger.error(f"❌ Error fetching user info: {e}")
            return {}

    def get_all_user_tasks(self, user_id: str) -> List[Dict]:
        """Get ALL tasks for the user (including deleted)"""
        logger.info(f"📋 Fetching ALL tasks for user: {user_id}")

        try:
            # Query all tasks for the user - no status filter to include deleted tasks
            query = self.db.collection('tasks').where('user_id', '==', user_id)
            docs = query.stream()

            tasks = []
            for doc in docs:
                task_data = doc.to_dict()
                task_data['id'] = doc.id
                tasks.append(task_data)

            logger.info(f"✅ Retrieved {len(tasks)} total tasks (including deleted)")
            return tasks

        except Exception as e:
            logger.error(f"❌ Error querying tasks: {e}")
            return []

    def analyze_task_statistics(self, tasks: List[Dict]) -> Dict:
        """Analyze task statistics"""
        stats = {
            'total_tasks': len(tasks),
            'by_status': {},
            'with_reminders': 0,
            'total_reminders': 0,
            'sent_reminders': 0,
            'pending_reminders': 0,
            'oldest_task': None,
            'newest_task': None
        }

        oldest_date = None
        newest_date = None

        for task in tasks:
            # Count by status
            status = task.get('status', 'unknown')
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

            # Check reminders
            reminders = task.get('reminders', [])
            if reminders:
                stats['with_reminders'] += 1
                stats['total_reminders'] += len(reminders)

                for reminder in reminders:
                    if reminder.get('sent', False):
                        stats['sent_reminders'] += 1
                    else:
                        stats['pending_reminders'] += 1

            # Track dates
            created_at = task.get('created_at')
            if created_at:
                try:
                    if hasattr(created_at, 'timestamp'):
                        task_date = created_at
                    else:
                        task_date = datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))

                    if oldest_date is None or task_date < oldest_date:
                        oldest_date = task_date
                        stats['oldest_task'] = {
                            'id': task['id'],
                            'title': task.get('title', 'No title'),
                            'date': self.format_timestamp(task_date)
                        }

                    if newest_date is None or task_date > newest_date:
                        newest_date = task_date
                        stats['newest_task'] = {
                            'id': task['id'],
                            'title': task.get('title', 'No title'),
                            'date': self.format_timestamp(task_date)
                        }
                except Exception as e:
                    logger.warning(f"⚠️ Error parsing date for task {task.get('id')}: {e}")

        return stats

    def print_task_details(self, task: Dict):
        """Print detailed information about a task"""
        print(f"\n📋 Task ID: {task['id']}")
        print(f"   Title: {task.get('title', 'No title')}")
        print(f"   Status: {task.get('status', 'unknown')}")
        print(f"   Priority: {task.get('priority', 'not set')}")
        print(f"   Description: {task.get('description', 'No description')[:100]}{'...' if len(task.get('description', '')) > 100 else ''}")
        print(f"   Created: {self.format_timestamp(task.get('created_at'))}")
        print(f"   Updated: {self.format_timestamp(task.get('updated_at'))}")
        print(f"   Due Date: {self.format_timestamp(task.get('due_date'))}")

        # Categories and tags
        if task.get('category'):
            print(f"   Category: {task.get('category')}")
        if task.get('tags'):
            print(f"   Tags: {', '.join(task.get('tags', []))}")

        # Completion info
        if task.get('status') == 'completed':
            print(f"   Completed: {self.format_timestamp(task.get('completed_at'))}")

        # Archive info
        if task.get('archived'):
            print(f"   Archived: {self.format_timestamp(task.get('archived_at'))}")

        # Reminders
        reminders = task.get('reminders', [])
        if reminders:
            print(f"   📱 Reminders ({len(reminders)}):")
            for i, reminder in enumerate(reminders, 1):
                print(f"      {i}. Time: {self.format_timestamp(reminder.get('reminder_time'))}")
                print(f"         Message: {reminder.get('message', 'No message')}")
                print(f"         Sent: {'✅ Yes' if reminder.get('sent', False) else '❌ No'}")
                if reminder.get('id'):
                    print(f"         ID: {reminder.get('id')}")
                if reminder.get('type'):
                    print(f"         Type: {reminder.get('type')}")
                print()
        else:
            print("   📱 No reminders")

    def print_user_summary(self, user_data: Dict):
        """Print user summary information"""
        if not user_data:
            print("❌ No user data found")
            return

        print("\n" + "="*80)
        print("👤 USER INFORMATION")
        print("="*80)
        print(f"User ID: {user_data.get('uid', 'Not found')}")
        print(f"Email: {user_data.get('email', 'Not found')}")
        print(f"Display Name: {user_data.get('display_name', 'Not set')}")
        print(f"Created: {self.format_timestamp(user_data.get('created_at'))}")

        # Preferences
        preferences = user_data.get('preferences', {})
        if preferences:
            print(f"\n⚙️ PREFERENCES:")
            print(f"   Timezone: {preferences.get('timezone', 'Not set')}")

            notification_prefs = preferences.get('notification_preferences', {})
            if notification_prefs:
                print(f"   📱 Notifications:")
                print(f"      Email: {notification_prefs.get('email', 'Not set')}")
                print(f"      Push: {notification_prefs.get('push', 'Not set')}")
                print(f"      Reminder Advance: {notification_prefs.get('reminder_advance', 'Not set')} minutes")

        # FCM Tokens
        tokens = user_data.get('fcm_tokens', [])
        if tokens:
            print(f"\n📱 FCM TOKENS ({len(tokens)}):")
            for i, token in enumerate(tokens, 1):
                print(f"   {i}. {token[:50]}...")

    def print_statistics(self, stats: Dict):
        """Print task statistics"""
        print("\n" + "="*80)
        print("📊 TASK STATISTICS")
        print("="*80)
        print(f"Total Tasks: {stats['total_tasks']}")

        print(f"\n📋 By Status:")
        for status, count in stats['by_status'].items():
            print(f"   {status}: {count}")

        print(f"\n📱 Reminders:")
        print(f"   Tasks with reminders: {stats['with_reminders']}")
        print(f"   Total reminders: {stats['total_reminders']}")
        print(f"   Sent reminders: {stats['sent_reminders']}")
        print(f"   Pending reminders: {stats['pending_reminders']}")

        if stats['oldest_task']:
            print(f"\n📅 Oldest Task:")
            print(f"   {stats['oldest_task']['title']} ({stats['oldest_task']['date']})")

        if stats['newest_task']:
            print(f"\n📅 Newest Task:")
            print(f"   {stats['newest_task']['title']} ({stats['newest_task']['date']})")

    def query_user_data(self, user_id: str):
        """Main method to query and display all user data"""
        print("🔍 FIREBASE FIRESTORE QUERY RESULTS")
        print("="*80)
        print(f"Target User ID: {user_id}")
        print(f"Query Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Get user information
        user_data = self.get_user_info(user_id)
        self.print_user_summary(user_data)

        # Get all tasks
        tasks = self.get_all_user_tasks(user_id)

        if not tasks:
            print("\n❌ No tasks found for this user")
            return

        # Analyze statistics
        stats = self.analyze_task_statistics(tasks)
        self.print_statistics(stats)

        # Print detailed task information
        print("\n" + "="*80)
        print("📋 DETAILED TASK INFORMATION")
        print("="*80)

        # Group tasks by status for better organization
        tasks_by_status = {}
        for task in tasks:
            status = task.get('status', 'unknown')
            if status not in tasks_by_status:
                tasks_by_status[status] = []
            tasks_by_status[status].append(task)

        # Display tasks grouped by status
        for status, status_tasks in tasks_by_status.items():
            print(f"\n🏷️ {status.upper()} TASKS ({len(status_tasks)})")
            print("-" * 40)

            # Sort by created_at (newest first)
            status_tasks.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)

            for task in status_tasks:
                self.print_task_details(task)

        # Save detailed output to file
        self.save_to_file(user_id, user_data, tasks, stats)

    def save_to_file(self, user_id: str, user_data: Dict, tasks: List[Dict], stats: Dict):
        """Save detailed results to a JSON file"""
        output_data = {
            'query_info': {
                'user_id': user_id,
                'query_time': datetime.now().isoformat(),
                'total_tasks': len(tasks)
            },
            'user_data': user_data,
            'statistics': stats,
            'tasks': tasks
        }

        filename = f"user_tasks_query_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, default=str, ensure_ascii=False)

            print(f"\n💾 Detailed results saved to: {filename}")

        except Exception as e:
            logger.error(f"❌ Error saving to file: {e}")

def main():
    """Main function"""
    target_user_id = "dGpDR3AMYxWwIORfJok5M8gdzuv1"

    try:
        service = FirestoreTaskQueryService()
        service.query_user_data(target_user_id)

    except Exception as e:
        logger.error(f"❌ Error running query: {e}")
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()