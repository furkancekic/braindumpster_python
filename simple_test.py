#!/usr/bin/env python3
"""
Simple single test for recurring tasks
"""

from services.gemini_service import GeminiService
from datetime import datetime
import json

def simple_test():
    print("🧪 SIMPLE RECURRING TASK TEST")
    print("=" * 40)

    gemini_service = GeminiService()

    user_context = {
        'user_id': 'test-user',
        'recent_tasks': [],
        'preferences': {},
        'current_date': datetime.now().strftime('%Y-%m-%d'),
        'current_time': datetime.now().strftime('%H:%M')
    }

    message = "I want to exercise 3 times a week for the next year."
    print(f"Message: {message}")
    print("Expected: 156 reminders (3 × 52 weeks)")
    print("-" * 40)

    try:
        result = gemini_service.generate_tasks_from_message(
            user_message=message,
            user_context=user_context
        )

        if result.get('success'):
            tasks = result.get('tasks', [])
            if tasks:
                task = tasks[0]
                reminders = task.get('reminders', [])
                is_recurring = task.get('is_recurring', False)
                pattern = task.get('recurring_pattern', {})

                print(f"✅ Success!")
                print(f"📋 Title: {task.get('title', 'N/A')}")
                print(f"🔄 Is Recurring: {is_recurring}")
                print(f"📊 Total Reminders: {len(reminders)}")

                if pattern:
                    print(f"📈 Total Occurrences: {pattern.get('total_occurrences', 'N/A')}")
                    print(f"🔁 Frequency: {pattern.get('frequency', 'N/A')}")

                if reminders:
                    print(f"📅 First: {reminders[0].get('reminder_time', 'N/A')}")
                    if len(reminders) > 1:
                        print(f"📅 Last: {reminders[-1].get('reminder_time', 'N/A')}")

                # Success criteria
                if len(reminders) >= 50 and is_recurring:
                    print("🎉 SUCCESS! Created 50+ reminders and marked as recurring!")
                elif len(reminders) >= 20:
                    print("⚠️ PARTIAL SUCCESS - Good number of reminders but check recurring flag")
                else:
                    print(f"❌ FAILED - Only {len(reminders)} reminders (need 50+)")
            else:
                print("❌ No tasks created")
        else:
            print(f"❌ Failed: {result.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"💥 Exception: {str(e)}")

if __name__ == "__main__":
    simple_test()