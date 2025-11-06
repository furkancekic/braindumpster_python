import google.generativeai as genai
from config import Config
from prompts.gemini_prompts import TASK_CREATION_PROMPT, CONTEXT_ANALYSIS_PROMPT
from typing import Dict, List, Optional
import json
import re
import logging
import time
import threading
from datetime import datetime, timedelta

class GeminiService:
    def __init__(self):
        self.logger = logging.getLogger('braindumpster.gemini')
        self.logger.info("🤖 Initializing GeminiService...")
        
        genai.configure(api_key=Config.GEMINI_API_KEY)
        # Use Gemini 2.0 Flash Exp - only model that works with File API in v1beta
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # Connection management
        self._last_request_time = 0
        self._request_lock = threading.Lock()
        self._max_retries = 3
        self._retry_delay = 1.0  # seconds
        self._request_timeout = 60.0  # seconds
        self._min_request_interval = 0.5  # seconds between requests
        
        self.logger.info("✅ GeminiService initialized with model: gemini-2.0-flash-exp")
    
    def _make_request_with_retry(self, request_func, *args, **kwargs):
        """Make a request to Gemini API with retry logic and rate limiting"""
        with self._request_lock:
            # Rate limiting - ensure minimum interval between requests
            current_time = time.time()
            time_since_last_request = current_time - self._last_request_time
            
            if time_since_last_request < self._min_request_interval:
                sleep_time = self._min_request_interval - time_since_last_request
                self.logger.debug(f"🕐 Rate limiting: waiting {sleep_time:.2f}s before next request")
                time.sleep(sleep_time)
            
            self._last_request_time = time.time()
        
        # Retry logic
        for attempt in range(self._max_retries):
            try:
                self.logger.debug(f"🚀 Making Gemini API request (attempt {attempt + 1}/{self._max_retries})")
                
                # Make the request with timeout
                start_time = time.time()
                response = request_func(*args, **kwargs)
                duration = time.time() - start_time
                
                self.logger.info(f"✅ Gemini API request completed in {duration:.2f}s")
                return response
                
            except Exception as e:
                error_msg = str(e)
                self.logger.warning(f"⚠️ Gemini API request failed (attempt {attempt + 1}/{self._max_retries}): {error_msg}")
                
                # Check if this is a retryable error
                if self._is_retryable_error(error_msg):
                    if attempt < self._max_retries - 1:
                        retry_delay = self._retry_delay * (2 ** attempt)  # Exponential backoff
                        self.logger.info(f"🔄 Retrying in {retry_delay:.2f}s...")
                        time.sleep(retry_delay)
                        continue
                
                # If we've exhausted retries or it's not retryable, raise the exception
                self.logger.error(f"❌ Gemini API request failed after {self._max_retries} attempts: {error_msg}")
                raise
        
        # This should never be reached
        raise Exception("Unexpected error in retry logic")
    
    def _is_retryable_error(self, error_msg: str) -> bool:
        """Check if an error is retryable"""
        retryable_errors = [
            "timeout",
            "connection",
            "network",
            "503",  # Service unavailable
            "502",  # Bad gateway
            "429",  # Too many requests
            "500",  # Internal server error
        ]
        
        error_lower = error_msg.lower()
        return any(retryable_error in error_lower for retryable_error in retryable_errors)
    
    def _create_fresh_model(self):
        """Create a fresh model instance for connection issues"""
        try:
            self.logger.info("🔄 Creating fresh Gemini model instance...")
            # Use Gemini 2.0 Flash Exp - only model that works with File API in v1beta
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
            self.logger.info("✅ Fresh Gemini model created successfully")
        except Exception as e:
            self.logger.error(f"❌ Failed to create fresh Gemini model: {str(e)}")
            raise
    
    def health_check(self) -> bool:
        """Check if Gemini service is healthy"""
        self.logger.debug("🏥 Performing Gemini health check")
        
        try:
            # Make a simple test request
            test_prompt = "Health check - respond with 'OK'"
            response = self._make_request_with_retry(self.model.generate_content, test_prompt)
            
            if response and response.text:
                self.logger.debug("✅ Gemini health check passed")
                return True
            else:
                self.logger.warning("⚠️ Gemini health check failed - empty response")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Gemini health check failed: {str(e)}")
            return False
        
    def generate_tasks_from_message(self, user_message: str, user_context: Dict) -> Dict:
        """Generate tasks and reminders from user message with context"""
        self.logger.info(f"💬 Processing text message from user...")
        self.logger.debug(f"📝 User message: {user_message}")
        self.logger.debug(f"🗂️ User context: {json.dumps(user_context, indent=2, default=str)}")
        
        try:
            prompt = self._build_task_creation_prompt(user_message, user_context)
            self.logger.debug(f"📋 Generated prompt (first 500 chars): {prompt[:500]}...")
            
            self.logger.info("🚀 Sending request to Gemini...")
            response = self._make_request_with_retry(self.model.generate_content, prompt)
            
            self.logger.info("✅ Received response from Gemini")
            self.logger.debug(f"📤 Gemini raw response: {response.text}")
            
            # Parse the structured response
            parsed_response = self._parse_gemini_response(response.text)
            self.logger.info(f"🎯 Parsed response successfully - Found {len(parsed_response.get('tasks', []))} tasks")
            
            return parsed_response
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"❌ Gemini API error: {error_msg}")
            
            # Check if this is a JSON parsing error from the _parse_gemini_response method
            if "JSONDecodeError" in error_msg or "json" in error_msg.lower():
                return {
                    "success": False,
                    "error": f"Response parsing error: {error_msg}",
                    "tasks": [],
                    "suggestions": [
                        {
                            "type": "information",
                            "title": "Response Processing Issue",
                            "description": "The AI response could not be processed correctly. Please try rephrasing your request or try again.",
                            "reasoning": "Technical issue with response format."
                        }
                    ]
                }
            else:
                # Other types of errors (network, API, etc.)
                return {
                    "success": False,
                    "error": f"Gemini API error: {error_msg}",
                    "tasks": [],
                    "suggestions": [
                        {
                            "type": "information",
                            "title": "Service Error",
                            "description": "There was an issue with the AI service. Please try again in a moment.",
                            "reasoning": "Temporary service issue."
                        }
                    ]
                }
    
    def generate_tasks_from_audio(self, audio_file_path: str, user_context: Dict) -> Dict:
        """Generate tasks and reminders from audio file with context"""
        self.logger.info(f"🎤 Processing audio file from user...")
        self.logger.debug(f"📁 Audio file path: {audio_file_path}")
        self.logger.debug(f"🗂️ User context: {json.dumps(user_context, indent=2, default=str)}")
        
        try:
            # Read audio file as bytes with proper file handling
            self.logger.info("📂 Reading audio file...")
            import os
            
            # Check file size first
            file_size = os.path.getsize(audio_file_path)
            max_file_size = 10 * 1024 * 1024  # 10MB limit
            
            if file_size > max_file_size:
                raise ValueError(f"Audio file too large: {file_size} bytes (max: {max_file_size} bytes)")
            
            with open(audio_file_path, 'rb') as audio_file:
                audio_data = audio_file.read()
            
            self.logger.info(f"✅ Audio file read successfully - {len(audio_data)} bytes")
            
            # Build context summary
            context_summary = self._summarize_context(user_context)
            self.logger.debug(f"📋 Context summary: {context_summary}")
            
            # Create prompt for audio processing
            self.logger.info("📝 Building audio processing prompt...")
            audio_prompt = f"""
You are an AI task scheduler and productivity assistant. I will provide you an audio recording where the user tells me their plans, tasks, or ideas.

IMPORTANT: Always respond in the same language as the user's audio. If they speak in Turkish, respond in Turkish. If in English, respond in English, etc.

Current Context:
- Date: {datetime.now().strftime("%Y-%m-%d")}
- Time: {datetime.now().strftime("%H:%M")}
- User's Previous Context: {context_summary}

Please listen to the audio and follow the same guidelines as text messages:

FIRST, determine if this is an information query or a task request:
- Information queries: Questions about existing data (tasks, reminders, status)
- Task requests: Requests to DO something new or create new plans

If it's an information query:
- Set query_type to "information_query" in the analysis
- List all relevant information from the context in the existing_reminders_summary field
- Return empty tasks array
- Provide a helpful summary of existing tasks/reminders in the suggestions section

If it's a task request, create a structured task plan.

REMINDER RULES:
- NEVER use 00:00 (midnight) 
- Use waking hours: 7:00 AM - 10:00 PM
- For tasks with dates, create 2-3 reminders before due date
- Space reminders at least 2 hours apart

CRITICAL RULES FOR DUPLICATE DETECTION:
- Before creating any task, carefully examine existing tasks for:
  * Same or similar activity (cooking, reading, walking, working, etc.)
  * Same or overlapping time periods (morning, afternoon, evening, specific hours)
  * Same location or context (garden, office, kitchen, etc.)
- If a task already exists for the same time period and similar activity, DO NOT create a new task
- Instead, set query_type to "duplicate_found" and include the existing task details in a special "existing_task" field

SUGGESTIONS REQUIREMENT:
- ALWAYS provide at least 1-3 helpful suggestions in EVERY response
- Suggestions help users optimize their tasks and workflow
- Types of suggestions to provide:
  * "optimization" - Ways to make the task more efficient or effective
  * "alternative" - Alternative approaches or methods
  * "additional" - Related tasks or considerations they might have missed
  * "information" - Helpful context, tips, or warnings
- Examples:
  * For a workout task → Suggest warmup routine, hydration reminder, rest days
  * For a study task → Suggest break intervals, resource materials, review schedule
  * For a work task → Suggest time blocking, eliminating distractions, deadlines
  * For any task → Suggest related habits, complementary activities, potential obstacles
- Even for simple tasks, provide at least one helpful suggestion
- Make suggestions specific and actionable, not generic

Return your response in the following JSON format:

```json
{{
  "success": true,
  "transcription": "Exact transcription of what the user said in the audio",
  "analysis": {{
    "user_intent": "Brief description of what the user wants to accomplish",
    "query_type": "information_query|task_request|duplicate_found",
    "key_priorities": ["Priority 1", "Priority 2", "Priority 3"],
    "time_frame": "Estimated time frame for completion",
    "complexity_assessment": "Simple/Medium/Complex",
    "existing_reminders_summary": "Summary of existing reminders if user asked about them",
    "existing_task": {{
      "title": "Task title if duplicate found",
      "description": "Task description if duplicate found", 
      "due_date": "YYYY-MM-DD HH:MM if duplicate found",
      "priority": "low|medium|high|urgent if duplicate found",
      "category": "work|personal|health|learning|social|other if duplicate found",
      "estimated_duration": "Duration in minutes if duplicate found",
      "reminders": [
        {{
          "reminder_time": "YYYY-MM-DD HH:MM",
          "message": "Reminder message",
          "type": "deadline|preparation|follow_up"
        }}
      ]
    }}
  }},
  "tasks": [
    {{
      "title": "Task title",
      "description": "Detailed description of what needs to be done",
      "priority": "low|medium|high|urgent",
      "estimated_duration": "Duration in minutes",
      "due_date": "YYYY-MM-DD HH:MM or null",
      "category": "work|personal|health|learning|social|other",
      "reminders": [
        {{
          "reminder_time": "YYYY-MM-DD HH:MM",
          "message": "Reminder message",
          "type": "deadline|preparation|follow_up"
        }}
      ]
    }}
  ],
  "suggestions": [
    {{
      "type": "optimization|alternative|additional|information",
      "title": "Suggestion title", 
      "description": "Detailed suggestion or information about existing tasks/reminders",
      "reasoning": "Why this suggestion might be helpful"
    }}
  ],
  "next_steps": [
    "Immediate next action the user should take",
    "Second priority action",
    "Third priority action"
  ]
}}
```

CRITICAL REQUIREMENTS:
- ALWAYS include the "transcription" field with the exact text the user spoke
- ALWAYS include the "tasks" array (even if empty)
- ALWAYS respond in the same language as the user's audio
- Ensure the JSON structure is complete and valid
"""
            
            # Create audio part for Gemini with proper MIME type detection
            self.logger.debug("🎵 Creating audio part for Gemini API...")
            
            # Detect audio file format more accurately
            import os
            file_extension = os.path.splitext(audio_file_path)[1].lower()
            
            # Map file extension to proper MIME type
            mime_type_mapping = {
                '.m4a': 'audio/mp4',
                '.aac': 'audio/aac', 
                '.wav': 'audio/wav',
                '.mp3': 'audio/mpeg',
                '.ogg': 'audio/ogg'
            }
            
            mime_type = mime_type_mapping.get(file_extension, 'audio/mp4')  # Default to mp4 for m4a files
            self.logger.info(f"🎵 Detected file extension: {file_extension}, using MIME type: {mime_type}")
            
            audio_part = {
                "mime_type": mime_type,
                "data": audio_data
            }
            
            self.logger.info("🚀 Sending audio request to Gemini...")
            response = self._make_request_with_retry(self.model.generate_content, [audio_prompt, audio_part])
            
            self.logger.info("✅ Received audio response from Gemini")
            self.logger.debug(f"📤 Gemini audio raw response: {response.text}")
            
            # Parse the structured response
            parsed_response = self._parse_gemini_response(response.text)
            self.logger.info(f"🎯 Parsed audio response successfully - Found {len(parsed_response.get('tasks', []))} tasks")
            
            # Ensure transcription is included in response
            if 'transcription' not in parsed_response:
                # Extract transcription from the response if available
                transcription = self._extract_transcription_from_response(response.text)
                parsed_response['transcription'] = transcription
                self.logger.info(f"📝 Added transcription to response: {transcription[:100]}...")
            
            return parsed_response
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"❌ Gemini Audio API error: {error_msg}")
            
            # Check if this is a JSON parsing error
            if "JSONDecodeError" in error_msg or "json" in error_msg.lower():
                return {
                    "success": False,
                    "error": f"Audio response parsing error: {error_msg}",
                    "tasks": [],
                    "suggestions": [
                        {
                            "type": "information",
                            "title": "Audio Processing Issue",
                            "description": "The audio response could not be processed correctly. Please try recording again or rephrase your request.",
                            "reasoning": "Technical issue with audio response format."
                        }
                    ]
                }
            else:
                return {
                    "success": False,
                    "error": f"Gemini Audio API error: {error_msg}",
                    "tasks": [],
                    "suggestions": [
                        {
                            "type": "information",
                            "title": "Audio Service Error",
                            "description": "There was an issue processing your audio. Please try again in a moment.",
                            "reasoning": "Temporary audio service issue."
                        }
                    ]
                }
    
    def transcribe_audio(self, audio_file_path: str) -> str:
        """Transcribe audio file to text using Gemini"""
        self.logger.info(f"🎤📝 Transcribing audio file...")
        self.logger.debug(f"📁 Audio file path: {audio_file_path}")
        
        try:
            # Read audio file as bytes with proper file handling
            self.logger.info("📂 Reading audio file for transcription...")
            import os
            
            # Check file size first
            file_size = os.path.getsize(audio_file_path)
            max_file_size = 10 * 1024 * 1024  # 10MB limit
            
            if file_size > max_file_size:
                raise ValueError(f"Audio file too large: {file_size} bytes (max: {max_file_size} bytes)")
            
            with open(audio_file_path, 'rb') as audio_file:
                audio_data = audio_file.read()
            
            self.logger.info(f"✅ Audio file read for transcription - {len(audio_data)} bytes")
            
            # Simple transcription prompt
            transcription_prompt = """
Please transcribe this audio recording to text. Return only the transcribed text without any additional commentary or formatting.
"""
            
            # Create audio part for Gemini with proper MIME type
            self.logger.debug("🎵 Creating audio part for transcription...")
            # DEEP FIX: Use WAV MIME type (changed from AAC to WAV for MediaCodec bypass)
            mime_type = "audio/wav"
            self.logger.info(f"🎵 Using MIME type: {mime_type} for file: {audio_file_path}")
            audio_part = {
                "mime_type": mime_type,
                "data": audio_data
            }
            
            self.logger.info("🚀 Sending transcription request to Gemini...")
            response = self._make_request_with_retry(self.model.generate_content, [transcription_prompt, audio_part])
            
            self.logger.info("✅ Received transcription response from Gemini")
            transcribed_text = response.text.strip()
            self.logger.debug(f"📝 Transcribed text: {transcribed_text}")
            
            # Return the transcribed text
            return transcribed_text
            
        except Exception as e:
            self.logger.error(f"❌ Transcription error: {str(e)}")
            return f"[Transcription error: {str(e)}]"
    
    
    def analyze_context_for_suggestions(self, user_context: Dict) -> Dict:
        """Analyze user context to provide proactive suggestions"""
        self.logger.info("🔍 Analyzing user context for proactive suggestions...")
        self.logger.debug(f"🗂️ Context data: {json.dumps(user_context, indent=2, default=str)}")
        
        try:
            prompt = self._build_context_analysis_prompt(user_context)
            self.logger.debug(f"📝 Generated context analysis prompt (first 500 chars): {prompt[:500]}...")
            
            self.logger.info("🚀 Sending context analysis request to Gemini...")
            response = self.model.generate_content(prompt)
            
            self.logger.info("✅ Received context analysis response from Gemini")
            self.logger.debug(f"📤 Gemini context analysis raw response: {response.text}")
            
            parsed_response = self._parse_gemini_response(response.text)
            self.logger.info(f"🎯 Parsed context analysis successfully - Found {len(parsed_response.get('suggestions', []))} suggestions")
            
            return parsed_response
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"❌ Context analysis error: {error_msg}")
            
            # Check if this is a JSON parsing error
            if "JSONDecodeError" in error_msg or "json" in error_msg.lower():
                return {
                    "success": False,
                    "error": f"Context analysis parsing error: {error_msg}",
                    "suggestions": [
                        {
                            "type": "information",
                            "title": "Analysis Processing Issue",
                            "description": "The context analysis response could not be processed correctly. Please try again.",
                            "reasoning": "Technical issue with analysis response format."
                        }
                    ]
                }
            else:
                return {
                    "success": False,
                    "error": f"Context analysis error: {error_msg}",
                    "suggestions": [
                        {
                            "type": "information",
                            "title": "Analysis Service Error",
                            "description": "There was an issue analyzing your context. Please try again in a moment.",
                            "reasoning": "Temporary analysis service issue."
                        }
                    ]
                }
    
    def _build_task_creation_prompt(self, user_message: str, user_context: Dict) -> str:
        """Build the task creation prompt with context"""
        context_summary = self._summarize_context(user_context)

        # Debug: Log context summary for duplicate detection
        self.logger.debug(f"🔍 DEBUG: Context summary length: {len(context_summary)} chars")
        self.logger.debug(f"🔍 DEBUG: Context summary preview: {context_summary[:200]}...")

        final_prompt = TASK_CREATION_PROMPT.format(
            user_message=user_message,
            context_summary=context_summary,
            current_date=datetime.now().strftime("%Y-%m-%d"),
            current_time=datetime.now().strftime("%H:%M")
        )

        # Log the full prompt being sent to Gemini
        print("\n" + "="*80)
        print("🤖 GEMINI PROMPT BEING SENT:")
        print("="*80)
        print(final_prompt)
        print("="*80 + "\n")

        return final_prompt
    
    
    def _build_context_analysis_prompt(self, user_context: Dict) -> str:
        """Build the context analysis prompt"""
        context_summary = self._summarize_context(user_context)
        
        return CONTEXT_ANALYSIS_PROMPT.format(
            context_summary=context_summary,
            current_date=datetime.now().strftime("%Y-%m-%d"),
            current_time=datetime.now().strftime("%H:%M")
        )
    
    def _summarize_context(self, user_context: Dict) -> str:
        """Summarize user context for prompts - simplified to avoid JSON parsing issues"""
        summary_parts = []
        
        # Recent tasks - simplified
        recent_tasks = user_context.get("recent_tasks", [])
        if recent_tasks:
            task_count = len(recent_tasks)
            summary_parts.append(f"Recent tasks: {task_count} tasks")
            
            # Just show task titles for duplicate detection
            task_titles = []
            for task in recent_tasks[:5]:  # Limit to 5 tasks
                title = task.get('title', 'Untitled')
                status = task.get('status', 'active')
                task_titles.append(f"{title} ({status})")
            
            if task_titles:
                summary_parts.append(f"Tasks: {', '.join(task_titles)}")
        
        # Reminders - simplified
        all_reminders = []
        for task in recent_tasks:
            task_reminders = task.get('reminders', [])
            for reminder in task_reminders:
                if not reminder.get('sent', False):
                    all_reminders.append(reminder.get('reminder_time', ''))
        
        if all_reminders:
            reminder_count = len(all_reminders)
            summary_parts.append(f"Upcoming reminders: {reminder_count}")
        
        # Keep it simple
        final_summary = ". ".join(summary_parts) if summary_parts else "No previous context"
        self.logger.debug(f"🔍 DEBUG: Simplified context summary: {final_summary}")
        return final_summary
    
    def _parse_gemini_response(self, response_text: str) -> Dict:
        """Parse structured response from Gemini with strict JSON validation"""
        self.logger.debug("🔧 Parsing Gemini response...")
        
        try:
            # Look for JSON block in the response
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                self.logger.debug("✅ Found JSON block in response")
                json_str = json_match.group(1).strip()
                
                # Parse the JSON strictly - no complex repair logic
                parsed_data = json.loads(json_str)
                self.logger.debug(f"✅ Successfully parsed JSON with {len(parsed_data.get('tasks', []))} tasks")
                
                # Validate and enhance the response
                validated_response = self._validate_and_enhance_response(parsed_data)
                return validated_response
            
            # If no JSON block found, try to parse the entire response as JSON
            self.logger.debug("🔄 No JSON block found, trying to parse entire response...")
            cleaned_response = response_text.strip()
            parsed_data = json.loads(cleaned_response)
            self.logger.debug(f"✅ Successfully parsed entire response as JSON with {len(parsed_data.get('tasks', []))} tasks")
            
            # Validate and enhance the response
            validated_response = self._validate_and_enhance_response(parsed_data)
            return validated_response
            
        except json.JSONDecodeError as e:
            # If JSON parsing fails, return error response
            self.logger.error(f"❌ JSON parsing failed: {str(e)}")
            self.logger.debug(f"📝 Raw response that failed to parse: {response_text[:500]}...")
            
            # Return structured error response
            return self._create_error_response(str(e), response_text)
            
        except Exception as e:
            self.logger.error(f"❌ Unexpected error in response parsing: {str(e)}")
            return self._create_error_response(str(e), response_text)
    
    def _create_error_response(self, error_msg: str, original_text: str) -> Dict:
        """Create a standardized error response"""
        try:
            user_intent = self._extract_user_intent_from_broken_response(original_text)
            
            return {
                "success": False,
                "detected_language": "en",  # Default to English for error responses
                "error": f"Gemini API error: {error_msg}",
                "analysis": {
                    "user_intent": user_intent,
                    "query_type": "parse_error",
                    "error_details": error_msg,
                    "raw_response_preview": original_text[:200] + "..." if len(original_text) > 200 else original_text
                },
                "tasks": [],
                "suggestions": [
                    {
                        "type": "information",
                        "title": "Response Processing Error",
                        "description": "The AI response format was invalid. Please try rephrasing your request.",
                        "reasoning": "Gemini did not return properly formatted JSON."
                    }
                ]
            }
        except Exception as e:
            self.logger.error(f"❌ Error creating error response: {e}")
            return {
                "success": False,
                "error": "Critical parsing error",
                "analysis": {"user_intent": "Unable to process", "query_type": "critical_error"},
                "tasks": [],
                "suggestions": []
            }
    
    
    def _extract_user_intent_from_broken_response(self, response_text: str) -> str:
        """Extract user intent from a broken response as a fallback"""
        try:
            # Look for common patterns that might indicate user intent
            patterns = [
                r'user_intent["\s]*:["\s]*([^"]*)',
                r'intent["\s]*:["\s]*([^"]*)',
                r'wants to ([^"]*)',
                r'user wants ([^"]*)',
                r'trying to ([^"]*)',
                r'planning to ([^"]*)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    intent = match.group(1).strip()
                    if intent and len(intent) > 3:
                        return intent
            
            # If no specific intent found, try to extract from the first readable sentence
            sentences = response_text.split('.')
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) > 20 and 'error' not in sentence.lower():
                    return sentence[:100] + "..." if len(sentence) > 100 else sentence
            
            return "Request could not be processed"
            
        except Exception as e:
            self.logger.warning(f"⚠️ Could not extract user intent: {e}")
            return "Unable to determine user intent"
    
    def _extract_transcription_from_response(self, response_text: str) -> str:
        """Extract transcription from Gemini response if available"""
        try:
            # Look for common transcription patterns in the response
            import re
            
            # Try to find transcription in the analysis section
            transcription_patterns = [
                r'"transcription"\s*:\s*"([^"]+)"',
                r'"user_intent"\s*:\s*"([^"]+)"',
                r'transcribed[^:]*:\s*"([^"]+)"',
                r'user said[^:]*:\s*"([^"]+)"'
            ]
            
            for pattern in transcription_patterns:
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    return match.group(1)
            
            # If no specific transcription found, try to extract from user_intent
            if 'user_intent' in response_text:
                intent_match = re.search(r'"user_intent"\s*:\s*"([^"]+)"', response_text)
                if intent_match:
                    return intent_match.group(1)
            
            # Fallback: return a portion of the response
            return "Audio message processed"
            
        except Exception as e:
            self.logger.warning(f"⚠️ Could not extract transcription: {e}")
            return "[Transcription not available]"
    
    def _validate_and_enhance_response(self, parsed_data: Dict) -> Dict:
        """Validate and enhance the parsed Gemini response for proper processing"""
        self.logger.debug("🔍 Validating and enhancing Gemini response...")
        
        # Ensure required structure exists
        validated_response = {
            "success": parsed_data.get("success", True),
            "detected_language": parsed_data.get("detected_language", "en"),
            "analysis": parsed_data.get("analysis", {}),
            "tasks": parsed_data.get("tasks", []),
            "suggestions": parsed_data.get("suggestions", []),
            "next_steps": parsed_data.get("next_steps", []),
            "transcription": parsed_data.get("transcription", "")
        }
        
        # Validate analysis section
        analysis = validated_response["analysis"]
        if not isinstance(analysis, dict):
            analysis = {}
            validated_response["analysis"] = analysis
        
        # Ensure required analysis fields
        analysis.setdefault("user_intent", "Unknown intent")
        analysis.setdefault("query_type", "task_request")
        analysis.setdefault("key_priorities", [])
        analysis.setdefault("time_frame", "")
        analysis.setdefault("complexity_assessment", "medium")
        
        # Handle duplicate detection
        query_type = analysis.get("query_type", "task_request")
        self.logger.debug(f"🔍 DEBUG: Query type detected: {query_type}")
        
        if query_type == "duplicate_found":
            self.logger.info("🔍 Duplicate task detected by Gemini")
            
            # Extract existing task details - should be structured JSON now
            existing_task = analysis.get("existing_task", {})
            self.logger.debug(f"🔍 DEBUG: Existing task details: {existing_task}")
            
            # Clear tasks array since we found a duplicate
            validated_response["tasks"] = []
            
            # Create proper duplicate information for suggestions
            if isinstance(existing_task, dict) and existing_task.get("title"):
                # Format task details nicely for display
                task_details = f"**{existing_task.get('title', 'Unnamed Task')}**"
                if existing_task.get('description'):
                    task_details += f"\nDescription: {existing_task.get('description')}"
                if existing_task.get('due_date'):
                    task_details += f"\nDue: {existing_task.get('due_date')}"
                if existing_task.get('priority'):
                    task_details += f"\nPriority: {existing_task.get('priority')}"
                    
                reminders = existing_task.get('reminders', [])
                if reminders:
                    task_details += f"\nReminders: {len(reminders)} scheduled"
                
                duplicate_suggestion = {
                    "type": "information", 
                    "title": "Duplicate Task Detected",
                    "description": f"A similar task already exists:\n\n{task_details}",
                    "reasoning": "This prevents duplicate tasks and helps maintain organization"
                }
            else:
                # Fallback for string format or missing data
                duplicate_suggestion = {
                    "type": "information",
                    "title": "Duplicate Task Detected", 
                    "description": f"A similar task already exists: {existing_task}",
                    "reasoning": "This prevents duplicate tasks and helps maintain organization"
                }
            
            validated_response["suggestions"].insert(0, duplicate_suggestion)
            
            # Add to next steps
            validated_response["next_steps"] = [
                "Review the existing similar task mentioned above",
                "Modify the existing task if needed instead of creating a new one",
                "Check your task list for other similar activities"
            ]
            
            self.logger.info("✅ Duplicate detection handled - tasks cleared, suggestions updated")
        
        # Validate and enhance tasks
        validated_tasks = []
        for i, task in enumerate(validated_response["tasks"]):
            if not isinstance(task, dict):
                self.logger.warning(f"⚠️ Task {i} is not a dictionary, skipping")
                continue
            
            # Validate task structure
            validated_task = {
                "title": task.get("title", f"Task {i+1}"),
                "description": task.get("description", ""),
                "priority": self._validate_priority(task.get("priority", "medium")),
                "estimated_duration": task.get("estimated_duration", "30"),
                "due_date": task.get("due_date"),
                "category": self._validate_category(task.get("category", "other")),
                "is_recurring": task.get("is_recurring", False),
                "recurring_pattern": task.get("recurring_pattern", {}),
                "reminders": []
            }
            
            # Validate and enhance reminders
            task_reminders = task.get("reminders", [])
            if isinstance(task_reminders, list):
                for reminder in task_reminders:
                    if isinstance(reminder, dict):
                        validated_reminder = {
                            "reminder_time": reminder.get("reminder_time"),
                            "message": reminder.get("message", f"Reminder for {validated_task['title']}"),
                            "type": self._validate_reminder_type(reminder.get("type", "preparation"))
                        }
                        
                        # Validate reminder time format
                        if validated_reminder["reminder_time"]:
                            try:
                                # Try to parse the reminder time to ensure it's valid
                                from datetime import datetime
                                datetime.fromisoformat(validated_reminder["reminder_time"].replace('Z', '+00:00'))
                                validated_task["reminders"].append(validated_reminder)
                            except ValueError:
                                self.logger.warning(f"⚠️ Invalid reminder time format: {validated_reminder['reminder_time']}")
            
            # Validate and fix due date and reminder timing issues
            validated_task = self._validate_due_date_and_reminders(validated_task)
            
            validated_tasks.append(validated_task)
            
        validated_response["tasks"] = validated_tasks
        
        # Validate suggestions
        validated_suggestions = []
        for suggestion in validated_response["suggestions"]:
            if isinstance(suggestion, dict):
                validated_suggestion = {
                    "type": self._validate_suggestion_type(suggestion.get("type", "additional")),
                    "title": suggestion.get("title", "Suggestion"),
                    "description": suggestion.get("description", ""),
                    "reasoning": suggestion.get("reasoning", "")
                }
                validated_suggestions.append(validated_suggestion)
        
        validated_response["suggestions"] = validated_suggestions
        
        # Validate next steps
        if not isinstance(validated_response["next_steps"], list):
            validated_response["next_steps"] = []
        
        # Check for time conflicts in reminders
        self._check_reminder_conflicts(validated_response)
        
        # Log detected language for debugging
        detected_lang = validated_response.get("detected_language", "unknown")
        self.logger.info(f"🌍 Language detected: {detected_lang}")
        self.logger.info(f"✅ Response validated - {len(validated_response['tasks'])} tasks, {len(validated_response['suggestions'])} suggestions")
        return validated_response
    
    def _validate_due_date_and_reminders(self, task: Dict) -> Dict:
        """Validate and fix due date and reminder timing issues"""
        try:
            if not task.get("due_date") or not task.get("reminders"):
                return task
            
            from datetime import datetime
            
            # Parse due date
            due_date_str = task["due_date"]
            if isinstance(due_date_str, str):
                if due_date_str.endswith('Z'):
                    due_date_str = due_date_str[:-1] + '+00:00'
                due_date = datetime.fromisoformat(due_date_str)
                
                # Check if due date is set to midnight (00:00)
                if due_date.hour == 0 and due_date.minute == 0:
                    # Fix: Change midnight to end of day (23:59)
                    fixed_due_date = due_date.replace(hour=23, minute=59, second=59)
                    task["due_date"] = fixed_due_date.strftime("%Y-%m-%d %H:%M")
                    self.logger.info(f"🔧 Fixed midnight due date to end of day: {task['due_date']}")
                    due_date = fixed_due_date
                
                # Validate all reminders are before due date
                fixed_reminders = []
                for reminder in task["reminders"]:
                    if reminder.get("reminder_time"):
                        reminder_time_str = reminder["reminder_time"]
                        if isinstance(reminder_time_str, str):
                            if reminder_time_str.endswith('Z'):
                                reminder_time_str = reminder_time_str[:-1] + '+00:00'
                            reminder_time = datetime.fromisoformat(reminder_time_str)
                            
                            # Check if reminder is after due date
                            if reminder_time <= due_date:
                                fixed_reminders.append(reminder)
                                self.logger.debug(f"✅ Reminder OK: {reminder_time_str}")
                            else:
                                self.logger.warning(f"⚠️ Skipping reminder after due date: {reminder_time_str} > {task['due_date']}")
                        else:
                            fixed_reminders.append(reminder)
                    else:
                        fixed_reminders.append(reminder)
                
                task["reminders"] = fixed_reminders
                
                # If no valid reminders remain, create a default one
                if not fixed_reminders and task.get("title"):
                    default_reminder_time = due_date.replace(hour=9, minute=0, second=0)
                    if default_reminder_time < due_date:
                        default_reminder = {
                            "reminder_time": default_reminder_time.strftime("%Y-%m-%d %H:%M"),
                            "message": f"Don't forget: {task['title']}",
                            "type": "preparation"
                        }
                        task["reminders"] = [default_reminder]
                        self.logger.info(f"🔧 Added default reminder: {default_reminder_time.strftime('%Y-%m-%d %H:%M')}")
                
        except Exception as e:
            self.logger.error(f"❌ Error validating due date and reminders: {e}")
            # Return task as-is if validation fails
        
        return task
    
    def _validate_priority(self, priority: str) -> str:
        """Validate task priority"""
        valid_priorities = ["low", "medium", "high", "urgent"]
        if priority.lower() in valid_priorities:
            return priority.lower()
        return "medium"
    
    def _validate_category(self, category: str) -> str:
        """Validate task category"""
        valid_categories = ["work", "personal", "health", "learning", "social", "other"]
        if category.lower() in valid_categories:
            return category.lower()
        return "other"
    
    def _validate_reminder_type(self, reminder_type: str) -> str:
        """Validate reminder type"""
        valid_types = ["deadline", "preparation", "follow_up"]
        if reminder_type.lower() in valid_types:
            return reminder_type.lower()
        return "preparation"
    
    def _validate_suggestion_type(self, suggestion_type: str) -> str:
        """Validate suggestion type"""
        valid_types = ["optimization", "alternative", "additional", "information"]
        if suggestion_type.lower() in valid_types:
            return suggestion_type.lower()
        return "additional"
    
    def _check_reminder_conflicts(self, validated_response: Dict) -> None:
        """Check for time conflicts in reminders and add warnings if found"""
        all_reminders = []
        
        # Collect all reminders from all tasks
        for task in validated_response["tasks"]:
            for reminder in task.get("reminders", []):
                if reminder.get("reminder_time"):
                    all_reminders.append({
                        "task_title": task["title"],
                        "reminder_time": reminder["reminder_time"],
                        "message": reminder["message"]
                    })
        
        if len(all_reminders) <= 1:
            return
        
        # Sort reminders by time
        try:
            from datetime import datetime
            all_reminders.sort(key=lambda r: datetime.fromisoformat(r["reminder_time"].replace('Z', '+00:00')))
        except ValueError:
            self.logger.warning("⚠️ Could not sort reminders by time due to format issues")
            return
        
        # Check for conflicts (reminders within 30 minutes of each other)
        conflicts = []
        for i in range(len(all_reminders) - 1):
            try:
                current_time = datetime.fromisoformat(all_reminders[i]["reminder_time"].replace('Z', '+00:00'))
                next_time = datetime.fromisoformat(all_reminders[i + 1]["reminder_time"].replace('Z', '+00:00'))
                
                time_diff = abs((next_time - current_time).total_seconds() / 60)  # Convert to minutes
                
                if time_diff < 30:  # Less than 30 minutes apart
                    conflicts.append({
                        "reminder1": all_reminders[i],
                        "reminder2": all_reminders[i + 1],
                        "time_diff": time_diff
                    })
            except ValueError:
                continue
        
        # Add conflict warnings to suggestions
        if conflicts:
            self.logger.warning(f"⚠️ Found {len(conflicts)} reminder time conflicts")
            
            conflict_suggestion = {
                "type": "optimization",
                "title": "Reminder Time Conflicts Detected",
                "description": f"Found {len(conflicts)} reminder(s) scheduled too close together (less than 30 minutes apart). Consider spacing them out for better effectiveness.",
                "reasoning": "Reminders work best when spaced at least 30 minutes apart to avoid notification fatigue"
            }
            
            validated_response["suggestions"].insert(0, conflict_suggestion)
            
            # Add details about conflicts
            for conflict in conflicts:
                conflict_detail = {
                    "type": "information",
                    "title": "Time Conflict Details",
                    "description": f"'{conflict['reminder1']['task_title']}' and '{conflict['reminder2']['task_title']}' have reminders only {conflict['time_diff']:.1f} minutes apart",
                    "reasoning": "Consider adjusting reminder times to improve effectiveness"
                }
                validated_response["suggestions"].append(conflict_detail)

    def analyze_audio_recording(self, audio_data: bytes, duration: int, current_date: str, mime_type: str = "audio/mp4"):
        """
        Analyze audio recording for meetings/lectures using Gemini

        Args:
            audio_data: Audio file data in bytes
            duration: Duration in seconds
            current_date: Current date string
            mime_type: MIME type of the audio file (audio/mpeg for MP3, audio/mp4 for M4A, etc.)
        """
        file_size_mb = len(audio_data) / (1024 * 1024)
        self.logger.info(f"🎤 Analyzing audio recording - {file_size_mb:.2f} MB, {duration}s, MIME: {mime_type}")

        try:
            from prompts.gemini_prompts import MEETING_ANALYSIS_PROMPT
            import tempfile
            import os
            import google.generativeai as genai

            # Create prompt
            prompt = MEETING_ANALYSIS_PROMPT.format(
                current_date=current_date,
                duration=duration
            )

            # Use Gemini File API for files larger than 10MB (more efficient than inline data)
            if file_size_mb > 10:
                self.logger.info(f"📁 Using Gemini File API for large file ({file_size_mb:.2f} MB)")

                # Create temporary file
                file_extension = mime_type.split('/')[-1]
                if file_extension == 'mpeg':
                    file_extension = 'mp3'
                elif file_extension == 'mp4':
                    file_extension = 'm4a'

                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}')
                try:
                    # Write audio data to temp file
                    temp_file.write(audio_data)
                    temp_file.flush()
                    temp_file.close()

                    self.logger.info(f"📤 Uploading file to Gemini File API...")
                    # Upload file to Gemini
                    uploaded_file = genai.upload_file(path=temp_file.name, mime_type=mime_type)
                    self.logger.info(f"✅ File uploaded: {uploaded_file.name}")

                    # Wait for file to be processed
                    import time
                    while uploaded_file.state.name == "PROCESSING":
                        self.logger.info("⏳ Waiting for file to be processed...")
                        time.sleep(2)
                        uploaded_file = genai.get_file(uploaded_file.name)

                    if uploaded_file.state.name == "FAILED":
                        raise Exception(f"File processing failed: {uploaded_file.state}")

                    self.logger.info(f"🤖 Sending to Gemini for analysis...")
                    # Call Gemini API with uploaded file and optimized config for audio
                    generation_config = {
                        "temperature": 0.4,  # Lower temperature for more consistent transcription
                        "top_p": 0.95,
                        "top_k": 40,
                        "max_output_tokens": 65536,  # High limit for long transcripts (gemini-2.0 supports up to 65k)
                    }
                    response = self.model.generate_content(
                        [prompt, uploaded_file],
                        generation_config=generation_config
                    )

                    # Log response details
                    self.logger.info(f"✅ Gemini response received")
                    self.logger.info(f"   Response type: {type(response)}")
                    self.logger.info(f"   Has text: {hasattr(response, 'text')}")

                    response_text = response.text.strip()
                    self.logger.info(f"📝 Response length: {len(response_text)} chars")
                    self.logger.info(f"   First 500 chars: {response_text[:500]}")

                    # Delete uploaded file from Gemini
                    self.logger.info(f"🗑️ Deleting uploaded file from Gemini...")
                    genai.delete_file(uploaded_file.name)

                finally:
                    # Clean up temp file
                    if os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)
                        self.logger.info(f"🗑️ Cleaned up temp file")

            else:
                # Use inline data for smaller files (< 10MB)
                self.logger.info(f"📦 Using inline data for small file ({file_size_mb:.2f} MB)")
                import base64

                audio_part = {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64.b64encode(audio_data).decode("utf-8")
                    }
                }

                # Call Gemini API with optimized config for audio
                generation_config = {
                    "temperature": 0.4,  # Lower temperature for more consistent transcription
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 65536,  # High limit for long transcripts (gemini-2.0 supports up to 65k)
                }
                response = self.model.generate_content(
                    [prompt, audio_part],
                    generation_config=generation_config
                )
                response_text = response.text.strip()

            # Log response details for debugging
            self.logger.info(f"📝 Gemini response length: {len(response_text)} chars")
            self.logger.info(f"   First 500 chars: {response_text[:500]}")

            # DEBUG: Write full response to file for inspection
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', dir='/tmp', prefix='gemini_response_') as f:
                f.write(response_text)
                self.logger.info(f"🔍 Full Gemini response written to: {f.name}")

            # Extract JSON
            analysis_json = self._extract_json_from_response(response_text)

            if not analysis_json:
                self.logger.warning("⚠️ Gemini returned invalid JSON, using fallback structure")
                self.logger.warning(f"   Full response text (first 1000): {response_text[:1000]}")
                # Return a valid fallback structure
                analysis_json = self._create_fallback_analysis(duration, current_date)

            return {"success": True, "analysis": analysis_json}

        except Exception as e:
            self.logger.error(f"❌ Error analyzing recording: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _create_fallback_analysis(self, duration: int, current_date: str):
        """
        Create a fallback analysis structure when Gemini fails to return valid JSON
        Returns a valid but empty structure that iOS can parse
        """
        return {
            "metadata": {
                "detectedType": "personal",
                "suggestedTitle": f"Recording - {current_date}",
                "language": "en",
                "speakerCount": 0,
                "confidence": 0.0
            },
            "summary": {
                "brief": "Audio recording could not be analyzed. The recording may not contain speech or the content is unclear.",
                "detailed": "The AI was unable to extract meaningful content from this audio recording. This may happen if the recording contains only music, noise, or no clear speech. Please try recording again with clear audio.",
                "keyTakeaways": ["Recording could not be analyzed"]
            },
            "transcript": [],
            "actionItems": [],
            "decisions": [],
            "keyPoints": [],
            "sentiment": None,
            "topics": [],
            "questions": [],
            "nextSteps": []
        }

    def _extract_json_from_response(self, response_text: str):
        """
        Extract JSON from Gemini response
        Handles both ```json ... ``` blocks and raw JSON
        """
        import re
        import json

        try:
            # Log full response length for debugging
            self.logger.debug(f"📏 Full response length: {len(response_text)} chars")

            # Try multiple patterns to match JSON blocks
            patterns = [
                r'```json\n(.*?)\n```',  # Standard: ```json\n{...}\n```
                r'```json\s+(.*?)\s+```',  # With whitespace
                r'```json(.*?)```',  # No whitespace
                r'```\s*json\s*(.*?)```',  # Flexible whitespace
            ]

            self.logger.info(f"🔍 Trying {len(patterns)} regex patterns to extract JSON...")
            self.logger.info(f"   Response starts with: {repr(response_text[:50])}")
            self.logger.info(f"   Response ends with: {repr(response_text[-50:])}")

            for i, pattern in enumerate(patterns):
                self.logger.info(f"   Pattern {i+1}: {pattern}")
                json_match = re.search(pattern, response_text, re.DOTALL)
                if json_match:
                    self.logger.info(f"✅ Found JSON block with pattern {i+1}")
                    json_str = json_match.group(1).strip()
                    self.logger.info(f"📝 Extracted JSON length: {len(json_str)} chars")
                    self.logger.info(f"   First 100 chars: {json_str[:100]}")

                    if json_str:  # Make sure it's not empty
                        try:
                            parsed_data = json.loads(json_str)
                            self.logger.info(f"✅ Successfully parsed JSON from code block")
                            return parsed_data
                        except json.JSONDecodeError as e:
                            self.logger.warning(f"⚠️ Pattern {i+1} matched but JSON invalid: {str(e)}")
                            self.logger.warning(f"   JSON start: {json_str[:200]}")
                            continue  # Try next pattern
                    else:
                        self.logger.warning(f"⚠️ Pattern {i+1} matched but extracted empty string")
                        continue
                else:
                    self.logger.info(f"   Pattern {i+1} did not match")

            # If no JSON block found, try to parse the entire response as JSON
            self.logger.debug("🔄 No JSON block found, trying to parse entire response...")
            cleaned_response = response_text.strip()
            parsed_data = json.loads(cleaned_response)
            self.logger.debug(f"✅ Successfully parsed entire response as JSON")
            return parsed_data

        except json.JSONDecodeError as e:
            self.logger.error(f"❌ JSON parsing failed: {str(e)}")
            self.logger.error(f"📝 First 1000 chars of response: {response_text[:1000]}")
            self.logger.error(f"📝 Last 500 chars of response: {response_text[-500:]}")
            return None

        except Exception as e:
            self.logger.error(f"❌ Error extracting JSON: {str(e)}")
            self.logger.error(f"📝 Response preview: {response_text[:500]}")
            return None

    def chat_about_recording(self, prompt: str, user_message: str):
        """Chat with AI about a recording"""
        try:
            full_prompt = f"""{prompt}

User Question: {user_message}

Your Answer:"""
            response = self.model.generate_content(full_prompt)
            return {"success": True, "response": response.text.strip()}
        except Exception as e:
            self.logger.error(f"❌ Error in chat: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

