#!/usr/bin/env python3
"""
Debug script to check task fetching and Firebase connectivity
"""

import sys
import os
import json
from datetime import datetime

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def debug_firebase_connection():
    """Test Firebase connection and basic functionality"""
    print("=== FIREBASE CONNECTION TEST ===")
    
    try:
        from services.firebase_service import FirebaseService
        firebase_service = FirebaseService()
        
        # Check if Firebase is properly initialized
        if firebase_service.db is None:
            print("❌ Firebase not initialized - check firebase_config.json")
            return False
        
        print("✅ Firebase service initialized successfully")
        
        # Test health check
        health = firebase_service.health_check()
        if health:
            print("✅ Firebase health check passed")
        else:
            print("❌ Firebase health check failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Firebase connection error: {e}")
        return False

def debug_user_tasks(user_id="demo-user-123"):
    """Debug task fetching for a specific user"""
    print(f"\n=== TASK FETCHING DEBUG FOR USER: {user_id} ===")
    
    try:
        from services.firebase_service import FirebaseService
        firebase_service = FirebaseService()
        
        if firebase_service.db is None:
            print("❌ Firebase not available")
            return
        
        print("🔍 Fetching all tasks for user...")
        all_tasks = firebase_service.get_user_tasks(user_id)
        print(f"📊 Total tasks found: {len(all_tasks)}")
        
        if len(all_tasks) == 0:
            print("⚠️  No tasks found for this user")
            print("💡 Possible causes:")
            print("   1. User has no tasks in Firestore")
            print("   2. User ID mismatch")
            print("   3. Firestore query/index issues")
            print("   4. Network connectivity issues")
        else:
            print("\n📋 Task breakdown:")
            status_counts = {}
            priority_counts = {}
            
            for task in all_tasks:
                # Count by status
                status = task.get('status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
                
                # Count by priority
                priority = task.get('priority', 'unknown')
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
                
                # Print first few tasks for inspection
                if len([t for t in all_tasks if all_tasks.index(t) < 3]) < 3:
                    print(f"   📝 Task: {task.get('title', 'No title')}")
                    print(f"      Status: {task.get('status', 'No status')}")
                    print(f"      Priority: {task.get('priority', 'No priority')}")
                    print(f"      User ID: {task.get('user_id', 'No user_id')}")
                    print(f"      ID: {task.get('id', 'No ID')}")
                    print()
            
            print(f"📊 Status distribution: {status_counts}")
            print(f"📊 Priority distribution: {priority_counts}")
        
        # Test specific status queries
        print("\n🔍 Testing status-specific queries...")
        for status in ['pending', 'approved', 'completed', 'cancelled']:
            status_tasks = firebase_service.get_user_tasks(user_id, status=status)
            print(f"   {status}: {len(status_tasks)} tasks")
        
        return all_tasks
        
    except Exception as e:
        print(f"❌ Error fetching tasks: {e}")
        import traceback
        traceback.print_exc()
        return []

def debug_firestore_query():
    """Debug Firestore queries directly"""
    print("\n=== DIRECT FIRESTORE QUERY DEBUG ===")
    
    try:
        from services.firebase_service import FirebaseService
        firebase_service = FirebaseService()
        
        if firebase_service.db is None:
            print("❌ Firebase not available")
            return
        
        # Direct query to see all tasks in the collection
        print("🔍 Querying all tasks in Firestore (first 10)...")
        tasks_ref = firebase_service.db.collection('tasks').limit(10)
        docs = tasks_ref.stream()
        
        task_count = 0
        users_found = set()
        
        for doc in docs:
            task_count += 1
            task_data = doc.to_dict()
            user_id = task_data.get('user_id', 'NO_USER_ID')
            users_found.add(user_id)
            
            print(f"   📝 Task {task_count}:")
            print(f"      ID: {doc.id}")
            print(f"      Title: {task_data.get('title', 'No title')}")
            print(f"      User ID: {user_id}")
            print(f"      Status: {task_data.get('status', 'No status')}")
            print()
        
        print(f"📊 Total tasks found in collection: {task_count}")
        print(f"👥 Unique users found: {list(users_found)}")
        
        # Check for common user IDs
        common_user_ids = [
            "demo-user-123",
            "demo-user",
            "test-user",
            "user-1"
        ]
        
        print("\n🔍 Checking common user IDs...")
        for user_id in common_user_ids:
            user_tasks = firebase_service.get_user_tasks(user_id)
            if len(user_tasks) > 0:
                print(f"   ✅ Found {len(user_tasks)} tasks for {user_id}")
            else:
                print(f"   ❌ No tasks found for {user_id}")
        
    except Exception as e:
        print(f"❌ Error with direct Firestore query: {e}")
        import traceback
        traceback.print_exc()

def debug_dashboard_api_simulation():
    """Simulate the dashboard API calls"""
    print("\n=== DASHBOARD API SIMULATION ===")
    
    # Simulate the user ID generation from dashboard.html
    print("🧪 Simulating dashboard user ID logic...")
    
    # This mimics the JavaScript logic from dashboard.html
    import random
    import string
    
    # Simulate stored user ID (like localStorage)
    simulated_user_id = 'demo-user-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))
    print(f"📱 Simulated user ID: {simulated_user_id}")
    
    # Test the stats API endpoint logic
    try:
        from services.firebase_service import FirebaseService
        firebase_service = FirebaseService()
        
        if firebase_service.db is None:
            print("❌ Firebase not available for API simulation")
            return
        
        print("🔍 Simulating /api/tasks/stats/{user_id} endpoint...")
        all_tasks = firebase_service.get_user_tasks(simulated_user_id)
        
        stats = {
            "total": len(all_tasks),
            "pending": len([t for t in all_tasks if t.get('status') == 'pending']),
            "approved": len([t for t in all_tasks if t.get('status') == 'approved']), 
            "completed": len([t for t in all_tasks if t.get('status') == 'completed']),
            "cancelled": len([t for t in all_tasks if t.get('status') == 'cancelled'])
        }
        
        print(f"📊 Stats for {simulated_user_id}: {stats}")
        
        # Test the tasks list API endpoint logic
        print("🔍 Simulating /api/tasks/user/{user_id} endpoint...")
        tasks = firebase_service.get_user_tasks(simulated_user_id)
        print(f"📋 Tasks returned: {len(tasks)}")
        
        if len(tasks) == 0:
            print("💡 This explains why the dashboard shows 'No tasks found'")
        
    except Exception as e:
        print(f"❌ Error in API simulation: {e}")

def debug_with_existing_data():
    """Try to find any existing data in Firestore"""
    print("\n=== SEARCHING FOR EXISTING DATA ===")
    
    try:
        from services.firebase_service import FirebaseService
        firebase_service = FirebaseService()
        
        if firebase_service.db is None:
            print("❌ Firebase not available")
            return
        
        # Check users collection
        print("🔍 Checking users collection...")
        users_ref = firebase_service.db.collection('users').limit(5)
        users_docs = list(users_ref.stream())
        print(f"👥 Found {len(users_docs)} users")
        
        for doc in users_docs:
            user_data = doc.to_dict()
            print(f"   User: {doc.id} - {user_data.get('email', 'No email')}")
        
        # Check conversations collection
        print("\n🔍 Checking conversations collection...")
        conv_ref = firebase_service.db.collection('conversations').limit(5)
        conv_docs = list(conv_ref.stream())
        print(f"💬 Found {len(conv_docs)} conversations")
        
        for doc in conv_docs:
            conv_data = doc.to_dict()
            user_id = conv_data.get('user_id', 'No user_id')
            print(f"   Conversation: {doc.id} - User: {user_id}")
            
            # If we find conversations, check if that user has tasks
            if user_id and user_id != 'No user_id':
                user_tasks = firebase_service.get_user_tasks(user_id)
                print(f"      -> This user has {len(user_tasks)} tasks")
        
    except Exception as e:
        print(f"❌ Error searching for existing data: {e}")

def main():
    """Run all debug checks"""
    print("🐛 TASK DASHBOARD DEBUG TOOL")
    print("=" * 50)
    
    # Step 1: Test Firebase connection
    if not debug_firebase_connection():
        print("\n❌ Firebase connection failed. Cannot proceed with other tests.")
        return
    
    # Step 2: Debug task fetching for common user IDs
    debug_user_tasks()
    
    # Step 3: Debug direct Firestore queries
    debug_firestore_query()
    
    # Step 4: Simulate dashboard API calls
    debug_dashboard_api_simulation()
    
    # Step 5: Search for any existing data
    debug_with_existing_data()
    
    print("\n" + "=" * 50)
    print("🔍 DEBUG SUMMARY:")
    print("1. Check if Firebase connection is working")
    print("2. Check if tasks exist in Firestore for the user")
    print("3. Check if user ID in frontend matches backend")
    print("4. Check Firestore indexes and query permissions")
    print("5. Check browser console for JavaScript errors")
    print("\n💡 If no tasks are found, try:")
    print("   - Create a test task through the chat interface")
    print("   - Check Firestore console for data")
    print("   - Verify user authentication is working")

if __name__ == "__main__":
    main()