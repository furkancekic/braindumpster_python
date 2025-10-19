#!/usr/bin/env python3
"""
Script to clean all data for demo user
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.firebase_service import FirebaseService
from datetime import datetime

def clean_demo_user_data(user_id):
    """Clean all data for a specific user"""
    firebase_service = FirebaseService()
    
    if not firebase_service.db:
        print("Firebase is not configured. Cannot clean data.")
        return
    
    print(f"Cleaning data for user: {user_id}")
    
    # Delete all tasks
    try:
        tasks = firebase_service.db.collection('tasks').where('user_id', '==', user_id).stream()
        task_count = 0
        for doc in tasks:
            doc.reference.delete()
            task_count += 1
        print(f"Deleted {task_count} tasks")
    except Exception as e:
        print(f"Error deleting tasks: {e}")
    
    # Delete all conversations
    try:
        conversations = firebase_service.db.collection('conversations').where('user_id', '==', user_id).stream()
        conv_count = 0
        for doc in conversations:
            doc.reference.delete()
            conv_count += 1
        print(f"Deleted {conv_count} conversations")
    except Exception as e:
        print(f"Error deleting conversations: {e}")
    
    # Delete user preferences/data if exists
    try:
        user_doc = firebase_service.db.collection('users').document(user_id)
        if user_doc.get().exists:
            user_doc.delete()
            print("Deleted user document")
    except Exception as e:
        print(f"Error deleting user document: {e}")
    
    print("Demo user data cleaned successfully!")

if __name__ == "__main__":
    # The demo user ID from localStorage
    demo_user_id = "demo-user-1234567890"
    
    if len(sys.argv) > 1:
        demo_user_id = sys.argv[1]
    
    confirm = input(f"Are you sure you want to delete all data for user '{demo_user_id}'? (yes/no): ")
    if confirm.lower() == 'yes':
        clean_demo_user_data(demo_user_id)
    else:
        print("Operation cancelled.")