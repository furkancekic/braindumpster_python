#!/usr/bin/env python3
"""
Debug script to investigate reminder notification issues
"""
import os
import sys
import json
from datetime import datetime, timezone
import logging

# Add the current directory to path
sys.path.append(os.path.dirname(__file__))

from services.firebase_service import FirebaseService
from models.task import Task

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def inspect_firestore_data():
    """Inspect actual data in Firestore"""
    print("🔍 Starting Firestore data inspection...")
    
    firebase_service = FirebaseService()
    
    # Get the user ID from the logs
    user_id = "dGpDR3AMYxWwIORfJok5M8gdzuv1"
    
    print(f"\n📋 Getting tasks for user: {user_id}")
    tasks = firebase_service.get_user_tasks(user_id, status=['approved', 'pending'])
    
    print(f"✅ Found {len(tasks)} tasks")
    
    for task in tasks:
        print(f"\n📄 Task: {task.get('title', 'Unknown')}")
        print(f"   ID: {task.get('id')}")
        print(f"   Status: {task.get('status')}")
        
        reminders = task.get('reminders', [])
        print(f"   Reminders: {len(reminders)}")
        
        for i, reminder in enumerate(reminders):
            print(f"      Reminder {i+1}:")
            print(f"         ID: {reminder.get('id')} (type: {type(reminder.get('id'))})")
            print(f"         Task ID: {reminder.get('task_id')}")
            print(f"         Time: {reminder.get('reminder_time')} (type: {type(reminder.get('reminder_time'))})")
            print(f"         Message: {reminder.get('message')}")
            print(f"         Sent: {reminder.get('sent')} (type: {type(reminder.get('sent'))})")
            print(f"         Created: {reminder.get('created_at')}")

def test_task_conversion():
    """Test Task object conversion"""
    print("\n🔄 Testing Task object conversion...")
    
    firebase_service = FirebaseService()
    user_id = "dGpDR3AMYxWwIORfJok5M8gdzuv1"
    
    # Get raw task data
    tasks = firebase_service.get_user_tasks(user_id, status=['approved', 'pending'])
    
    for task_data in tasks:
        print(f"\n📄 Converting task: {task_data.get('title')}")
        
        try:
            # Convert to Task object
            task = Task.from_dict(task_data)
            
            print(f"   ✅ Conversion successful")
            print(f"   Task ID: {task.id}")
            print(f"   Status: {task.status}")
            print(f"   Reminders count: {len(task.reminders)}")
            
            for i, reminder in enumerate(task.reminders):
                print(f"      Reminder {i+1}:")
                print(f"         ID: {reminder.id} (type: {type(reminder.id)})")
                print(f"         Task ID: {reminder.task_id}")
                print(f"         Time: {reminder.reminder_time} (type: {type(reminder.reminder_time)})")
                print(f"         Message: {reminder.message}")
                print(f"         Sent: {reminder.sent} (type: {type(reminder.sent)})")
                
        except Exception as e:
            print(f"   ❌ Conversion failed: {e}")

def test_due_reminders():
    """Test the due reminders logic"""
    print("\n⏰ Testing due reminders logic...")
    
    firebase_service = FirebaseService()
    user_id = "dGpDR3AMYxWwIORfJok5M8gdzuv1"
    current_time = datetime.utcnow().replace(tzinfo=timezone.utc)
    
    print(f"Current time (UTC): {current_time}")
    
    # Get due reminders
    due_reminders = firebase_service.get_due_reminders(user_id, current_time)
    
    print(f"✅ Found {len(due_reminders)} due reminders")
    
    for i, reminder_data in enumerate(due_reminders):
        print(f"\n   Due Reminder {i+1}:")
        print(f"      Task ID: {reminder_data.get('task_id')}")
        print(f"      Reminder ID: {reminder_data.get('reminder_id')} (type: {type(reminder_data.get('reminder_id'))})")
        print(f"      Time: {reminder_data.get('reminder_time')}")
        print(f"      Message: {reminder_data.get('message')}")
        
        # Test matching logic
        print(f"\n      🔍 Testing matching logic for task {reminder_data.get('task_id')}:")
        
        # Get the task
        task_data = firebase_service.get_task(reminder_data.get('task_id'))
        if task_data:
            task = Task.from_dict(task_data)
            
            print(f"         Task has {len(task.reminders)} reminders")
            
            # Try to find matching reminder
            found_match = False
            for r in task.reminders:
                print(f"         Checking reminder: {r.id} vs {reminder_data['reminder_id']}")
                print(f"         Types: {type(r.id)} vs {type(reminder_data['reminder_id'])}")
                print(f"         Equal: {r.id == reminder_data['reminder_id']}")
                print(f"         Sent: {r.sent} (type: {type(r.sent)})")
                print(f"         Time check: {r.reminder_time} <= {current_time} = {r.reminder_time <= current_time}")
                
                if (r.id == reminder_data['reminder_id'] and 
                    not r.sent and 
                    r.reminder_time <= current_time):
                    print(f"         ✅ MATCH FOUND!")
                    found_match = True
                    break
                else:
                    reasons = []
                    if r.id != reminder_data['reminder_id']:
                        reasons.append("ID mismatch")
                    if r.sent:
                        reasons.append("already sent")
                    if r.reminder_time > current_time:
                        reasons.append("not due yet")
                    print(f"         ❌ No match: {', '.join(reasons)}")
            
            if not found_match:
                print(f"         ❌ NO MATCHING REMINDER FOUND!")
        else:
            print(f"         ❌ Task not found")

def main():
    """Main debug function"""
    print("🐛 Reminder Notification Debug Script")
    print("=" * 50)
    
    try:
        inspect_firestore_data()
        test_task_conversion()
        test_due_reminders()
        
        print("\n✅ Debug script completed successfully")
        
    except Exception as e:
        print(f"\n❌ Debug script failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()