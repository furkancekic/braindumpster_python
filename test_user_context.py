#!/usr/bin/env python3
"""
Test script to check if user context is being properly loaded
"""

from services.firebase_service import FirebaseService
from services.gemini_service import GeminiService
from datetime import datetime
import json

def test_user_context():
    """Test the user context loading and summarization"""

    print("🧪 TESTING USER CONTEXT LOADING")
    print("=" * 50)

    # Test user ID from the conversation summary
    test_user_id = "dGpDR3AMYxWwIORfJok5M8gdzuv1"

    try:
        # Initialize services
        firebase_service = FirebaseService()
        gemini_service = GeminiService()

        print(f"👤 Testing user context for: {test_user_id}")
        print("-" * 40)

        # Get user context from Firebase
        print("🔍 Step 1: Getting user context from Firebase...")
        user_context = firebase_service.get_user_context(test_user_id)

        print(f"✅ User context retrieved:")
        print(f"   Recent tasks: {len(user_context.get('recent_tasks', []))}")
        print(f"   Conversation history: {len(user_context.get('conversation_history', []))}")
        print(f"   User preferences: {len(user_context.get('user_preferences', {}))}")

        # Show first few tasks if available
        recent_tasks = user_context.get('recent_tasks', [])
        if recent_tasks:
            print(f"\n📋 First few tasks:")
            for i, task in enumerate(recent_tasks[:3]):
                print(f"   {i+1}. {task.get('title', 'No title')} ({task.get('status', 'unknown')})")
        else:
            print("📋 No recent tasks found")

        # Test Gemini service context summarization
        print(f"\n🔍 Step 2: Testing Gemini context summarization...")
        summary = gemini_service._summarize_context(user_context)
        print(f"📝 Context summary: '{summary}'")

        # Test with empty context
        print(f"\n🔍 Step 3: Testing with empty context...")
        empty_context = {"recent_tasks": [], "conversation_history": [], "user_preferences": {}}
        empty_summary = gemini_service._summarize_context(empty_context)
        print(f"📝 Empty context summary: '{empty_summary}'")

        # Show raw user context structure
        print(f"\n🔍 Step 4: Raw user context structure:")
        print(json.dumps({
            "recent_tasks_count": len(user_context.get('recent_tasks', [])),
            "conversation_history_count": len(user_context.get('conversation_history', [])),
            "user_preferences_keys": list(user_context.get('user_preferences', {}).keys()),
            "user_profile_keys": list(user_context.get('user_profile', {}).keys())
        }, indent=2))

        print(f"\n🎯 DIAGNOSIS:")
        if recent_tasks:
            print(f"✅ User has {len(recent_tasks)} tasks - context should be populated")
            print(f"📊 Summary should show task info: '{summary}'")
        else:
            print(f"⚠️ User has no tasks - 'No previous context' is expected")
            print(f"📊 Summary correctly shows: '{summary}'")

    except Exception as e:
        print(f"❌ Error testing user context: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_user_context()