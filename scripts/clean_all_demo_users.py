#!/usr/bin/env python3
"""
Script to clean all demo user data from Firebase
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.firebase_service import FirebaseService
from datetime import datetime

def clean_all_demo_users():
    """Clean all data for demo users (users starting with 'demo-user-')"""
    firebase_service = FirebaseService()
    
    if not firebase_service.db:
        print("Firebase is not configured. Cannot clean data.")
        return
    
    print("Cleaning all demo user data...")
    
    # Delete all tasks from demo users
    try:
        all_tasks = firebase_service.db.collection('tasks').stream()
        task_count = 0
        for doc in all_tasks:
            task_data = doc.to_dict()
            if task_data.get('user_id', '').startswith('demo-user-'):
                doc.reference.delete()
                task_count += 1
                print(f"Deleted task: {task_data.get('title', 'Untitled')} from user: {task_data.get('user_id')}")
        print(f"Total tasks deleted: {task_count}")
    except Exception as e:
        print(f"Error deleting tasks: {e}")
    
    # Delete all conversations from demo users
    try:
        all_conversations = firebase_service.db.collection('conversations').stream()
        conv_count = 0
        for doc in all_conversations:
            conv_data = doc.to_dict()
            if conv_data.get('user_id', '').startswith('demo-user-'):
                doc.reference.delete()
                conv_count += 1
                print(f"Deleted conversation from user: {conv_data.get('user_id')}")
        print(f"Total conversations deleted: {conv_count}")
    except Exception as e:
        print(f"Error deleting conversations: {e}")
    
    # Delete all demo user documents
    try:
        all_users = firebase_service.db.collection('users').stream()
        user_count = 0
        for doc in all_users:
            if doc.id.startswith('demo-user-'):
                doc.reference.delete()
                user_count += 1
                print(f"Deleted user document: {doc.id}")
        print(f"Total user documents deleted: {user_count}")
    except Exception as e:
        print(f"Error deleting user documents: {e}")
    
    print("\nAll demo user data cleaned successfully!")

if __name__ == "__main__":
    confirm = input("Are you sure you want to delete ALL demo user data? This cannot be undone! (yes/no): ")
    if confirm.lower() == 'yes':
        clean_all_demo_users()
    else:
        print("Operation cancelled.")