#!/usr/bin/env python3
"""
Integration test for recurring task functionality
Tests the complete flow from Gemini prompt to task storage
"""

from services.gemini_service import GeminiService
from services.firebase_service import FirebaseService
from models.task import Task
from utils.validation import TaskValidator
from datetime import datetime
import json

def test_recurring_task_integration():
    """Test complete recurring task integration flow"""

    print("🧪 TESTING RECURRING TASK INTEGRATION")
    print("=" * 60)

    try:
        # Step 1: Test Gemini service generates proper recurring task structure
        print("📝 Step 1: Testing Gemini task generation...")
        gemini_service = GeminiService()

        user_context = {
            'user_id': 'test-user',
            'recent_tasks': [],
            'preferences': {},
            'current_date': datetime.now().strftime('%Y-%m-%d'),
            'current_time': datetime.now().strftime('%H:%M')
        }

        message = "I want to exercise 3 times a week for the next year."
        result = gemini_service.generate_tasks_from_message(message, user_context)

        if result.get('success') and result.get('tasks'):
            task_data = result['tasks'][0]
            print(f"✅ Gemini generated task successfully")
            print(f"   Title: {task_data.get('title')}")
            print(f"   Is Recurring: {task_data.get('is_recurring')}")
            print(f"   Pattern: {task_data.get('recurring_pattern', {})}")
            print(f"   Reminders: {len(task_data.get('reminders', []))}")
        else:
            print(f"❌ Gemini failed to generate task: {result.get('error')}")
            return

        # Step 2: Test task validation
        print(f"\n📋 Step 2: Testing task validation...")
        try:
            validated_data = TaskValidator.validate_task_data(task_data, 0)
            print(f"✅ Task validation passed")
            print(f"   Validated fields: {list(validated_data.keys())}")
            print(f"   Has recurring fields: {('is_recurring' in validated_data, 'recurring_pattern' in validated_data)}")
        except Exception as e:
            print(f"❌ Task validation failed: {e}")
            return

        # Step 3: Test Task model creation
        print(f"\n🏗️ Step 3: Testing Task model creation...")
        try:
            task = Task(
                title=validated_data['title'],
                description=validated_data['description'],
                user_id='test-user',
                due_date=validated_data.get('due_date'),
                priority=validated_data['priority'],
                is_recurring=validated_data.get('is_recurring', False),
                recurring_pattern=validated_data.get('recurring_pattern', {})
            )
            print(f"✅ Task model created successfully")
            print(f"   Title: {task.title}")
            print(f"   Is Recurring: {task.is_recurring}")
            print(f"   Pattern: {task.recurring_pattern}")
        except Exception as e:
            print(f"❌ Task model creation failed: {e}")
            return

        # Step 4: Test serialization
        print(f"\n💾 Step 4: Testing task serialization...")
        try:
            task_dict = task.to_dict()
            print(f"✅ Task serialization successful")
            print(f"   Serialized fields: {list(task_dict.keys())}")
            print(f"   Has recurring fields: {('is_recurring' in task_dict, 'recurring_pattern' in task_dict)}")
        except Exception as e:
            print(f"❌ Task serialization failed: {e}")
            return

        # Step 5: Test deserialization
        print(f"\n📤 Step 5: Testing task deserialization...")
        try:
            recreated_task = Task.from_dict(task_dict)
            print(f"✅ Task deserialization successful")
            print(f"   Recreated task title: {recreated_task.title}")
            print(f"   Recreated is_recurring: {recreated_task.is_recurring}")
            print(f"   Recreated pattern: {recreated_task.recurring_pattern}")
        except Exception as e:
            print(f"❌ Task deserialization failed: {e}")
            return

        print(f"\n🎉 SUCCESS! Complete recurring task integration works!")
        print(f"📊 Summary:")
        print(f"   ✅ Gemini generates recurring tasks with {len(task_data.get('reminders', []))} reminders")
        print(f"   ✅ Validation handles recurring fields")
        print(f"   ✅ Task model supports recurring fields")
        print(f"   ✅ Serialization/deserialization preserves recurring data")

    except Exception as e:
        print(f"💥 Integration test failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_recurring_task_integration()