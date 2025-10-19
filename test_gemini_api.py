#!/usr/bin/env python3
"""
Comprehensive Gemini API Test Script
Tests API connectivity, configuration, and JSON response parsing
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import project modules
try:
    from config import Config
    from services.gemini_service import GeminiService
    import google.generativeai as genai
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this from the braindumpster_python directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GeminiAPITester:
    """Test suite for Gemini API functionality"""
    
    def __init__(self):
        self.results = {}
        self.service = None
        
    def print_header(self, title: str):
        """Print a formatted header"""
        print(f"\n{'='*60}")
        print(f"🧪 {title}")
        print(f"{'='*60}")
    
    def print_test_result(self, test_name: str, success: bool, details: str = ""):
        """Print test result with formatting"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"   {details}")
        self.results[test_name] = {"success": success, "details": details}
    
    def test_environment_setup(self):
        """Test 1: Environment and Configuration"""
        self.print_header("Environment & Configuration Tests")
        
        # Test 1.1: Check if API key is configured
        try:
            api_key = Config.GEMINI_API_KEY
            if api_key and api_key != "your_gemini_api_key_here":
                self.print_test_result("API Key Configuration", True, f"Key present (length: {len(api_key)})")
            else:
                self.print_test_result("API Key Configuration", False, "API key not configured or using default value")
                return False
        except AttributeError:
            self.print_test_result("API Key Configuration", False, "GEMINI_API_KEY not found in Config")
            return False
        
        # Test 1.2: Check if google-generativeai is installed
        try:
            import google.generativeai as genai
            self.print_test_result("Google GenerativeAI Package", True, f"Version: {genai.__version__ if hasattr(genai, '__version__') else 'Unknown'}")
        except ImportError as e:
            self.print_test_result("Google GenerativeAI Package", False, f"Import error: {e}")
            return False
        
        # Test 1.3: API key format validation
        if len(api_key) > 30 and api_key.startswith("AI"):
            self.print_test_result("API Key Format", True, "Key format looks valid")
        else:
            self.print_test_result("API Key Format", False, "API key format may be invalid")
        
        return True
    
    def test_api_connectivity(self):
        """Test 2: API Connectivity"""
        self.print_header("API Connectivity Tests")
        
        # Test 2.1: Initialize Gemini service
        try:
            self.service = GeminiService()
            self.print_test_result("Service Initialization", True, "GeminiService created successfully")
        except Exception as e:
            self.print_test_result("Service Initialization", False, f"Error: {e}")
            return False
        
        # Test 2.2: Health check
        try:
            health_status = self.service.health_check()
            self.print_test_result("Health Check", health_status, "API is responding" if health_status else "API not responding")
        except Exception as e:
            self.print_test_result("Health Check", False, f"Error: {e}")
            return False
        
        return True
    
    def test_direct_api_call(self):
        """Test 3: Direct API Call"""
        self.print_header("Direct API Call Tests")
        
        try:
            # Configure API directly
            genai.configure(api_key=Config.GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            
            # Test 3.1: Simple text generation
            test_prompt = "Respond with exactly: 'API test successful'"
            response = model.generate_content(test_prompt)
            
            if response and response.text:
                self.print_test_result("Direct API Call", True, f"Response: {response.text[:100]}...")
            else:
                self.print_test_result("Direct API Call", False, "No response received")
                return False
                
        except Exception as e:
            self.print_test_result("Direct API Call", False, f"Error: {e}")
            return False
        
        return True
    
    def test_json_response_parsing(self):
        """Test 4: JSON Response Parsing"""
        self.print_header("JSON Response Parsing Tests")
        
        if not self.service:
            self.print_test_result("JSON Parsing", False, "Service not initialized")
            return False
        
        # Test 4.1: Simple task creation
        try:
            test_message = "I need to buy groceries tomorrow"
            test_context = {
                "recent_tasks": [],
                "conversation_history": [],
                "user_preferences": {}
            }
            
            start_time = time.time()
            response = self.service.generate_tasks_from_message(test_message, test_context)
            end_time = time.time()
            
            # Check response structure
            if isinstance(response, dict):
                required_fields = ["success", "analysis", "tasks", "suggestions"]
                missing_fields = [field for field in required_fields if field not in response]
                
                if not missing_fields:
                    self.print_test_result("Response Structure", True, f"All required fields present. Time: {end_time - start_time:.2f}s")
                else:
                    self.print_test_result("Response Structure", False, f"Missing fields: {missing_fields}")
                    return False
                
                # Check if it's a successful response
                if response.get("success"):
                    self.print_test_result("Task Generation", True, f"Generated {len(response.get('tasks', []))} tasks")
                else:
                    self.print_test_result("Task Generation", False, f"Error: {response.get('error', 'Unknown error')}")
                    return False
                    
            else:
                self.print_test_result("Response Format", False, f"Response is not a dict: {type(response)}")
                return False
                
        except Exception as e:
            self.print_test_result("JSON Parsing", False, f"Error: {e}")
            return False
        
        return True
    
    def test_error_handling(self):
        """Test 5: Error Handling"""
        self.print_header("Error Handling Tests")
        
        if not self.service:
            self.print_test_result("Error Handling", False, "Service not initialized")
            return False
        
        # Test 5.1: Invalid input handling
        try:
            # Test with empty message
            response = self.service.generate_tasks_from_message("", {})
            if isinstance(response, dict) and "error" in response:
                self.print_test_result("Empty Input Handling", True, "Handled empty input gracefully")
            else:
                self.print_test_result("Empty Input Handling", True, "Generated response for empty input")
                
        except Exception as e:
            self.print_test_result("Empty Input Handling", False, f"Error: {e}")
        
        # Test 5.2: Large input handling
        try:
            large_message = "Test message. " * 1000  # Very long message
            response = self.service.generate_tasks_from_message(large_message, {})
            if isinstance(response, dict):
                self.print_test_result("Large Input Handling", True, "Handled large input")
            else:
                self.print_test_result("Large Input Handling", False, "Failed to handle large input")
                
        except Exception as e:
            self.print_test_result("Large Input Handling", False, f"Error: {e}")
        
        return True
    
    def test_audio_functionality(self):
        """Test 6: Audio Processing (if available)"""
        self.print_header("Audio Processing Tests")
        
        if not self.service:
            self.print_test_result("Audio Processing", False, "Service not initialized")
            return False
        
        # Check if there are any audio files to test with
        audio_dir = os.path.join(os.path.dirname(__file__), "voice_recordings")
        if os.path.exists(audio_dir):
            audio_files = []
            for root, dirs, files in os.walk(audio_dir):
                for file in files:
                    if file.endswith(('.wav', '.mp3', '.m4a', '.aac')):
                        audio_files.append(os.path.join(root, file))
                        break  # Just test with one file
            
            if audio_files:
                try:
                    test_audio = audio_files[0]
                    print(f"   Testing with: {os.path.basename(test_audio)}")
                    
                    response = self.service.generate_tasks_from_audio(test_audio, {})
                    if isinstance(response, dict) and "transcription" in response:
                        self.print_test_result("Audio Processing", True, f"Transcription: {response['transcription'][:50]}...")
                    else:
                        self.print_test_result("Audio Processing", False, "No transcription in response")
                        
                except Exception as e:
                    self.print_test_result("Audio Processing", False, f"Error: {e}")
            else:
                self.print_test_result("Audio Processing", False, "No audio files found for testing")
        else:
            self.print_test_result("Audio Processing", False, "No voice_recordings directory found")
        
        return True
    
    def test_performance(self):
        """Test 7: Performance Tests"""
        self.print_header("Performance Tests")
        
        if not self.service:
            self.print_test_result("Performance", False, "Service not initialized")
            return False
        
        # Test 7.1: Response time
        test_messages = [
            "I need to call my doctor",
            "Remind me to buy milk",
            "I want to learn Python programming",
            "Schedule a meeting with the team next week"
        ]
        
        times = []
        for i, message in enumerate(test_messages):
            try:
                start_time = time.time()
                response = self.service.generate_tasks_from_message(message, {})
                end_time = time.time()
                
                if isinstance(response, dict):
                    times.append(end_time - start_time)
                    print(f"   Test {i+1}: {end_time - start_time:.2f}s")
                else:
                    print(f"   Test {i+1}: Failed")
                    
            except Exception as e:
                print(f"   Test {i+1}: Error - {e}")
        
        if times:
            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)
            
            self.print_test_result("Response Time", True, f"Avg: {avg_time:.2f}s, Min: {min_time:.2f}s, Max: {max_time:.2f}s")
        else:
            self.print_test_result("Response Time", False, "No successful responses")
        
        return True
    
    def run_all_tests(self):
        """Run all tests"""
        print(f"🚀 Starting Gemini API Test Suite")
        print(f"📅 Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Run all tests
        tests = [
            self.test_environment_setup,
            self.test_api_connectivity,
            self.test_direct_api_call,
            self.test_json_response_parsing,
            self.test_error_handling,
            self.test_audio_functionality,
            self.test_performance
        ]
        
        for test in tests:
            try:
                test()
            except Exception as e:
                print(f"❌ Test suite error: {e}")
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        self.print_header("Test Summary")
        
        total_tests = len(self.results)
        passed_tests = sum(1 for result in self.results.values() if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"📊 Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"📈 Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print(f"\n❌ Failed Tests:")
            for test_name, result in self.results.items():
                if not result["success"]:
                    print(f"   - {test_name}: {result['details']}")
        
        print(f"\n🏁 Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def main():
    """Main function"""
    tester = GeminiAPITester()
    tester.run_all_tests()

if __name__ == "__main__":
    main()