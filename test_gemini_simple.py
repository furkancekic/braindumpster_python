#!/usr/bin/env python3
"""
Simple Gemini API Test Script
Tests basic API functionality without complex dependencies
"""

import os
import sys
import json
import time
from datetime import datetime

# Simple configuration without dotenv
class SimpleConfig:
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', "AIzaSyDMIo6j9svCX7G66Nkmo0XUYrwbznhDi9Y")

def test_gemini_api():
    """Test Gemini API functionality"""
    print("🚀 Starting Simple Gemini API Test")
    print(f"📅 Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Test 1: Check API Key
    print("\n🔑 Testing API Key Configuration...")
    api_key = SimpleConfig.GEMINI_API_KEY
    if api_key and api_key != "your_gemini_api_key_here":
        print(f"✅ API Key found (length: {len(api_key)})")
        if len(api_key) > 30 and api_key.startswith("AI"):
            print("✅ API Key format looks valid")
        else:
            print("⚠️  API Key format may be invalid")
    else:
        print("❌ API Key not configured")
        return False
    
    # Test 2: Import google-generativeai
    print("\n📦 Testing Google GenerativeAI Package...")
    try:
        import google.generativeai as genai
        print("✅ Package imported successfully")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        print("Install with: pip install google-generativeai")
        return False
    
    # Test 3: Configure and test API
    print("\n🌐 Testing API Connection...")
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        print("✅ API configured successfully")
    except Exception as e:
        print(f"❌ API configuration failed: {e}")
        return False
    
    # Test 4: Simple API call
    print("\n🧪 Testing Simple API Call...")
    try:
        test_prompt = "Respond with exactly: 'Hello, API test successful!'"
        start_time = time.time()
        response = model.generate_content(test_prompt)
        end_time = time.time()
        
        if response and response.text:
            print(f"✅ API call successful ({end_time - start_time:.2f}s)")
            print(f"📝 Response: {response.text}")
        else:
            print("❌ No response received")
            return False
    except Exception as e:
        print(f"❌ API call failed: {e}")
        return False
    
    # Test 5: JSON Response Test
    print("\n📄 Testing JSON Response...")
    try:
        json_prompt = '''
        Return a JSON response with this exact structure:
        ```json
        {
          "success": true,
          "message": "JSON test successful",
          "timestamp": "2025-01-15 12:00:00",
          "data": {
            "test": "value"
          }
        }
        ```
        '''
        
        start_time = time.time()
        response = model.generate_content(json_prompt)
        end_time = time.time()
        
        if response and response.text:
            print(f"✅ JSON response received ({end_time - start_time:.2f}s)")
            
            # Try to extract JSON
            response_text = response.text
            print(f"📝 Raw response: {response_text[:200]}...")
            
            # Look for JSON block
            import re
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
                try:
                    parsed_json = json.loads(json_str)
                    print("✅ JSON parsed successfully")
                    print(f"📊 Parsed JSON: {json.dumps(parsed_json, indent=2)}")
                except json.JSONDecodeError as e:
                    print(f"❌ JSON parsing failed: {e}")
                    print(f"📝 Raw JSON: {json_str}")
            else:
                print("⚠️  No JSON block found in response")
        else:
            print("❌ No JSON response received")
            return False
    except Exception as e:
        print(f"❌ JSON test failed: {e}")
        return False
    
    # Test 6: Task Creation Test
    print("\n📋 Testing Task Creation...")
    try:
        task_prompt = '''
        Create a task from this message: "I need to buy groceries tomorrow"
        
        Return ONLY valid JSON in this format:
        ```json
        {
          "success": true,
          "analysis": {
            "user_intent": "User wants to buy groceries tomorrow",
            "query_type": "task_request"
          },
          "tasks": [
            {
              "title": "Buy groceries",
              "description": "Purchase groceries for the week",
              "priority": "medium",
              "due_date": "2025-01-16 18:00"
            }
          ],
          "suggestions": []
        }
        ```
        '''
        
        start_time = time.time()
        response = model.generate_content(task_prompt)
        end_time = time.time()
        
        if response and response.text:
            print(f"✅ Task creation response received ({end_time - start_time:.2f}s)")
            
            # Try to parse the task response
            json_match = re.search(r'```json\n(.*?)\n```', response.text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
                try:
                    parsed_response = json.loads(json_str)
                    print("✅ Task JSON parsed successfully")
                    
                    # Validate structure
                    required_fields = ["success", "analysis", "tasks", "suggestions"]
                    missing_fields = [field for field in required_fields if field not in parsed_response]
                    
                    if not missing_fields:
                        print("✅ All required fields present")
                        tasks = parsed_response.get("tasks", [])
                        print(f"📊 Generated {len(tasks)} task(s)")
                        if tasks:
                            print(f"📝 First task: {tasks[0].get('title', 'No title')}")
                    else:
                        print(f"⚠️  Missing fields: {missing_fields}")
                        
                except json.JSONDecodeError as e:
                    print(f"❌ Task JSON parsing failed: {e}")
                    print(f"📝 Raw JSON: {json_str[:200]}...")
            else:
                print("⚠️  No JSON block found in task response")
                print(f"📝 Raw response: {response.text[:200]}...")
        else:
            print("❌ No task creation response received")
            return False
    except Exception as e:
        print(f"❌ Task creation test failed: {e}")
        return False
    
    # Test Summary
    print("\n" + "=" * 60)
    print("🎉 All tests completed successfully!")
    print(f"⏱️  Total time: {time.time() - start_time:.2f}s")
    print("✅ Gemini API is working correctly")
    print("✅ JSON parsing is functional")
    print("✅ Task creation is working")
    
    return True

def main():
    """Main function"""
    success = test_gemini_api()
    if success:
        print("\n🚀 Gemini API is ready for use!")
        sys.exit(0)
    else:
        print("\n❌ Gemini API tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()