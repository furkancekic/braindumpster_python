#!/usr/bin/env python3
"""
Test script for the enhanced recurring task prompt
"""

from services.gemini_service import GeminiService
from datetime import datetime
import json

def test_recurring_task_prompt():
    """Test the enhanced recurring task prompt with various scenarios"""

    # Initialize Gemini service
    gemini_service = GeminiService()

    test_cases = [
        {
            "name": "Exercise 3 times a week for next year",
            "message": "I want to exercise 3 times a week for the next year. I plan to go one day and rest one day alternately.",
            "expected": "Should create 156 reminders (52 weeks × 3 days)"
        },
        {
            "name": "Daily meditation for 6 months",
            "message": "I want to meditate every day for the next 6 months. 30 minutes each morning.",
            "expected": "Should create 180 daily reminders (6 months × 30 days)"
        },
        {
            "name": "Weekly meeting every Friday",
            "message": "Schedule weekly team meetings every Friday for the next quarter.",
            "expected": "Should create 12-13 weekly reminders"
        },
        {
            "name": "Turkish recurring task",
            "message": "Spor yapacağım haftada 3 gün, önümüzdeki yıl boyunca. Bir gün gidip bir gün dinleneceğim.",
            "expected": "Should create 156 reminders for Turkish input"
        }
    ]

    print("🧪 TESTING ENHANCED RECURRING TASK PROMPT")
    print("=" * 60)

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 Test Case {i}: {test_case['name']}")
        print(f"📝 Message: {test_case['message']}")
        print(f"🎯 Expected: {test_case['expected']}")
        print("-" * 40)

        try:
            # Create task using Gemini service
            user_context = {
                'user_id': 'test-user',
                'recent_tasks': [],
                'preferences': {},
                'current_date': datetime.now().strftime('%Y-%m-%d'),
                'current_time': datetime.now().strftime('%H:%M')
            }

            result = gemini_service.generate_tasks_from_message(
                user_message=test_case['message'],
                user_context=user_context
            )

            if result.get('success'):
                tasks = result.get('tasks', [])
                print(f"✅ Success! Created {len(tasks)} task(s)")

                for j, task in enumerate(tasks, 1):
                    print(f"\n   Task {j}:")
                    print(f"   Title: {task.get('title', 'N/A')}")
                    print(f"   Description: {task.get('description', 'N/A')}")
                    print(f"   Is Recurring: {task.get('is_recurring', False)}")

                    if task.get('is_recurring'):
                        pattern = task.get('recurring_pattern', {})
                        print(f"   Frequency: {pattern.get('frequency', 'N/A')}")
                        print(f"   Total Occurrences: {pattern.get('total_occurrences', 'N/A')}")

                    reminders = task.get('reminders', [])
                    print(f"   Total Reminders: {len(reminders)}")

                    if reminders:
                        print(f"   First Reminder: {reminders[0].get('reminder_time', 'N/A')}")
                        if len(reminders) > 1:
                            print(f"   Last Reminder: {reminders[-1].get('reminder_time', 'N/A')}")

                # Print raw JSON for debugging
                print(f"\n🔍 Raw Response:")
                print(json.dumps(result, indent=2, ensure_ascii=False))

            else:
                print(f"❌ Failed: {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"💥 Exception: {str(e)}")

        print("\n" + "=" * 60)

if __name__ == "__main__":
    test_recurring_task_prompt()