#!/usr/bin/env python3
"""
Simple notification test - shows how to test once you have Firebase token
"""
import requests
import json
import time
from datetime import datetime, timedelta

def test_with_firebase_token(firebase_token, fcm_token):
    """Test notifications with Firebase token"""
    base_url = "http://57.129.81.193:5000"
    
    print("🔐 Step 1: Verifying Firebase token...")
    
    # Verify token
    verify_response = requests.post(
        f"{base_url}/api/auth/verify",
        json={"id_token": firebase_token}
    )
    
    print(f"Token verification: {verify_response.status_code}")
    if verify_response.status_code != 200:
        print(f"❌ Token verification failed: {verify_response.text}")
        return False
    
    user_data = verify_response.json()
    user_id = user_data.get('uid')
    print(f"✅ Authenticated as: {user_id}")
    
    # Set up session with auth
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {firebase_token}"})
    
    print("\n📱 Step 2: Registering FCM token...")
    
    # Register FCM token
    fcm_response = session.post(
        f"{base_url}/api/notifications/register-token",
        json={"fcm_token": fcm_token}
    )
    
    print(f"FCM registration: {fcm_response.status_code}")
    print(f"Response: {fcm_response.text}")
    
    if fcm_response.status_code == 200:
        print("✅ FCM token registered!")
    else:
        print("❌ FCM registration failed")
        return False
    
    print("\n🔔 Step 3: Sending test notification...")
    
    # Send test notification
    test_response = session.post(
        f"{base_url}/api/notifications/test-notification",
        json={
            "title": "🧪 API Test Success!",
            "body": "Your push notification system is working!"
        }
    )
    
    print(f"Test notification: {test_response.status_code}")
    print(f"Response: {test_response.text}")
    
    if test_response.status_code == 200:
        print("✅ Test notification sent!")
        print("📱 CHECK YOUR PHONE NOW!")
        return True
    else:
        print("❌ Test notification failed")
        return False

def show_instructions():
    """Show instructions for getting Firebase token"""
    print("🚀 PUSH NOTIFICATION API TEST")
    print("=" * 50)
    print("📱 Your FCM Token: cXgbHq2EQmeYq2gvy1cu")
    print()
    print("🔥 TO TEST NOTIFICATIONS:")
    print()
    print("1️⃣ GET FIREBASE TOKEN FROM YOUR FLUTTER APP:")
    print("   Add this code to your Flutter app (e.g., in main.dart):")
    print()
    print("   ```dart")
    print("   // Add this where you handle authentication")
    print("   FirebaseAuth.instance.authStateChanges().listen((User? user) {")
    print("     if (user != null) {")
    print("       user.getIdToken().then((token) {")
    print("         print('🔑 FIREBASE TOKEN: $token');")
    print("       });")
    print("     }")
    print("   });")
    print("   ```")
    print()
    print("2️⃣ RUN WITH TOKEN:")
    print("   Once you get the token from Flutter app logs, run:")
    print("   python3 simple_notification_test.py YOUR_FIREBASE_TOKEN_HERE")
    print()
    print("3️⃣ WATCH YOUR PHONE:")
    print("   You should receive a push notification!")
    print()
    print("🎯 ALTERNATIVE - Quick Test via Flutter App:")
    print("   1. Open your Flutter app")
    print("   2. Go to notification settings")
    print("   3. Tap 'Test Notifications'")
    print("   4. Your FCM token will be registered automatically")
    print()
    
def main():
    import sys
    
    if len(sys.argv) > 1:
        firebase_token = sys.argv[1]
        fcm_token = "cXgbHq2EQmeYq2gvy1cu"
        
        print("🧪 Testing with provided Firebase token...")
        success = test_with_firebase_token(firebase_token, fcm_token)
        
        if success:
            print("\n🎉 SUCCESS! Your notification system is working!")
            print("📱 You should have received a push notification")
            print("🔔 Now you can create tasks in your app and get automatic reminders")
        else:
            print("\n❌ Test failed - check the error messages above")
    else:
        show_instructions()

if __name__ == "__main__":
    main()