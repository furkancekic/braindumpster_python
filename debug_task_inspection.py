#!/usr/bin/env python3
"""
Debug script to inspect task data structure in Firebase
"""
import sys
import os
sys.path.append('.')

from services.firebase_service import FirebaseService
import json
from datetime import datetime

def inspect_tasks():
    """Inspect all tasks in the database"""
    firebase_service = FirebaseService()
    
    if not firebase_service.db:
        print("❌ Firebase not configured")
        return
    
    print("🔍 INSPECTING FIREBASE TASKS DATABASE")
    print("=" * 60)
    
    # Get all tasks from the database
    try:
        # Direct query to see raw data structure
        all_tasks_ref = firebase_service.db.collection('tasks')
        docs = all_tasks_ref.limit(10).stream()  # Limit to 10 for inspection
        
        task_count = 0
        for doc in docs:
            task_count += 1
            task_data = doc.to_dict()
            
            print(f"\n📋 TASK {task_count}: {doc.id}")
            print(f"   Title: {task_data.get('title', 'N/A')}")
            print(f"   Status: {task_data.get('status', 'N/A')}")
            print(f"   User ID: {task_data.get('user_id', 'N/A')}")
            print(f"   Created: {task_data.get('created_at', 'N/A')}")
            print(f"   Updated: {task_data.get('updated_at', 'N/A')}")
            
            # Check reminders
            reminders = task_data.get('reminders', [])
            print(f"   📅 Reminders: {len(reminders)}")
            
            for i, reminder in enumerate(reminders):
                print(f"      Reminder {i+1}:")
                print(f"        ID: {reminder.get('id', 'N/A')}")
                print(f"        Time: {reminder.get('reminder_time', 'N/A')}")
                print(f"        Message: {reminder.get('message', 'N/A')}")
                print(f"        Sent: {reminder.get('sent', 'N/A')}")
                print(f"        Task ID: {reminder.get('task_id', 'N/A')}")
            
            # Show raw data structure
            print(f"   🗂️ Raw data keys: {list(task_data.keys())}")
            
            # Check if reminders field exists and what type it is
            if 'reminders' in task_data:
                print(f"   🔍 Reminders field type: {type(task_data['reminders'])}")
                print(f"   🔍 Reminders field value: {json.dumps(task_data['reminders'], indent=4, default=str)}")
            
            print("-" * 60)
        
        if task_count == 0:
            print("❌ No tasks found in database")
        else:
            print(f"\n✅ Inspected {task_count} tasks")
            
    except Exception as e:
        print(f"❌ Error inspecting tasks: {e}")

def inspect_specific_user_tasks(user_id: str):
    """Inspect tasks for a specific user"""
    firebase_service = FirebaseService()
    
    if not firebase_service.db:
        print("❌ Firebase not configured")
        return
    
    print(f"🔍 INSPECTING TASKS FOR USER: {user_id}")
    print("=" * 60)
    
    try:
        # Get tasks using the same method as the API
        tasks = firebase_service.get_user_tasks(user_id)
        
        print(f"📊 Found {len(tasks)} tasks for user")
        
        for i, task in enumerate(tasks):
            print(f"\n📋 TASK {i+1}: {task.get('id', 'N/A')}")
            print(f"   Title: {task.get('title', 'N/A')}")
            print(f"   Status: {task.get('status', 'N/A')}")
            print(f"   Due Date: {task.get('due_date', 'N/A')}")
            
            # Check reminders
            reminders = task.get('reminders', [])
            print(f"   📅 Reminders: {len(reminders)}")
            
            for j, reminder in enumerate(reminders):
                print(f"      Reminder {j+1}:")
                print(f"        ID: {reminder.get('id', 'N/A')}")
                print(f"        Time: {reminder.get('reminder_time', 'N/A')}")
                print(f"        Message: {reminder.get('message', 'N/A')}")
                print(f"        Sent: {reminder.get('sent', 'N/A')}")
                
                # Check if reminder time is in the future
                reminder_time_str = reminder.get('reminder_time')
                if reminder_time_str:
                    try:
                        reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                        now = datetime.utcnow().replace(tzinfo=reminder_time.tzinfo)
                        is_future = reminder_time > now
                        time_diff = reminder_time - now
                        print(f"        ⏰ Due in: {time_diff} (Future: {is_future})")
                    except Exception as e:
                        print(f"        ❌ Time parse error: {e}")
            
            print("-" * 40)
            
    except Exception as e:
        print(f"❌ Error inspecting user tasks: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
        inspect_specific_user_tasks(user_id)
    else:
        inspect_tasks()
        print("\n" + "=" * 60)
        print("💡 To inspect specific user tasks, run:")
        print("   python debug_task_inspection.py <user_id>")
        print("   Example: python debug_task_inspection.py dGpDR3AMYxWwIORfJok5M8gdzuv1")