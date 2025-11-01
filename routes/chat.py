from flask import Blueprint, request, jsonify, current_app
from services.firebase_service import FirebaseService
from services.gemini_service import GeminiService
from models.conversation import Conversation
from datetime import datetime
import os
import tempfile
from werkzeug.utils import secure_filename
import logging
import json
import threading
from functools import wraps
from contextlib import contextmanager

chat_bp = Blueprint('chat', __name__)

# Global concurrent request limiting
_concurrent_audio_requests = 0
_max_concurrent_audio_requests = 3
_audio_request_lock = threading.Lock()

def get_logger():
    return logging.getLogger('braindumpster.routes.chat')

@contextmanager
def audio_request_limiter():
    """Context manager to limit concurrent audio requests"""
    global _concurrent_audio_requests
    
    with _audio_request_lock:
        if _concurrent_audio_requests >= _max_concurrent_audio_requests:
            raise Exception(f"Too many concurrent audio requests ({_concurrent_audio_requests}). Please try again later.")
        
        _concurrent_audio_requests += 1
        get_logger().info(f"🎵 Audio request started ({_concurrent_audio_requests}/{_max_concurrent_audio_requests})")
    
    try:
        yield
    finally:
        with _audio_request_lock:
            _concurrent_audio_requests -= 1
            get_logger().info(f"🎵 Audio request completed ({_concurrent_audio_requests}/{_max_concurrent_audio_requests})")

@contextmanager
def secure_temp_file(user_id: str, extension: str = '.wav'):
    """Context manager for secure temporary file handling"""
    temp_dir = tempfile.gettempdir()
    filename = secure_filename(f"audio_{user_id}_{int(datetime.now().timestamp())}{extension}")
    audio_path = os.path.join(temp_dir, filename)
    
    logger = get_logger()
    logger.info(f"💾 Creating temporary file: {audio_path}")
    
    try:
        yield audio_path
    finally:
        # Always clean up temporary file
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                logger.info(f"🧹 Cleaned up temporary file: {audio_path}")
            except Exception as e:
                logger.error(f"❌ Failed to clean up temporary file {audio_path}: {str(e)}")
        else:
            logger.debug(f"🔍 Temporary file not found for cleanup: {audio_path}")

def require_auth(f):
    """Decorator to require authentication for endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger = get_logger()
        
        # Get authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning("❌ Missing or invalid Authorization header")
            return jsonify({"error": "Authorization required"}), 401
        
        # Extract token
        id_token = auth_header.split('Bearer ')[1]
        
        # Verify token with Firebase
        firebase_service = current_app.firebase_service
        decoded_token = firebase_service.verify_id_token(id_token)
        
        if not decoded_token:
            logger.warning("❌ Invalid or expired token")
            return jsonify({"error": "Invalid or expired token"}), 401
        
        # Add user info to request
        request.user_id = decoded_token.get('uid')
        request.user_email = decoded_token.get('email')
        
        logger.info(f"✅ Authenticated user: {request.user_email} ({request.user_id})")
        return f(*args, **kwargs)
    
    return decorated_function

@chat_bp.route('/send', methods=['POST'])
@require_auth
def send_message():
    logger = get_logger()
    logger.info("💬 Processing chat message...")
    
    try:
        data = request.get_json()
        # Security: Use authenticated user ID instead of request body
        user_id = request.user_id
        message = data.get('message')
        conversation_id = data.get('conversation_id')
        
        logger.info(f"👤 User ID: {user_id}")
        logger.info(f"💬 Conversation ID: {conversation_id}")
        logger.debug(f"📝 Message: {message}")
        
        if not message:
            logger.error("❌ Missing required field: message")
            return jsonify({"error": "message is required"}), 400
        
        firebase_service = current_app.firebase_service
        gemini_service = current_app.gemini_service
        
        # Get user context and existing tasks for duplicate detection
        logger.info("🔍 Getting user context...")
        user_context = firebase_service.get_user_context(user_id)

        # Get user's active tasks for duplicate detection
        logger.info("🔍 Getting user's active tasks for duplicate detection...")
        try:
            existing_tasks = firebase_service.get_user_tasks(user_id, status=['pending', 'approved'])
            user_context['existing_tasks'] = [
                {
                    'title': task.get('title', ''),
                    'description': task.get('description', ''),
                    'category': task.get('category', ''),
                    'id': task.get('id', '')
                }
                for task in existing_tasks[:10]  # Limit to recent 10 tasks for context
            ]
            logger.info(f"📋 Found {len(existing_tasks)} active tasks for duplicate detection")
        except Exception as e:
            logger.warning(f"⚠️ Failed to get existing tasks for duplicate detection: {e}")
            user_context['existing_tasks'] = []
        
        # Get or create conversation
        if conversation_id:
            # Load existing conversation
            conversations = firebase_service.get_user_conversations(user_id)
            conversation_data = next((c for c in conversations if c['id'] == conversation_id), None)
            if not conversation_data:
                return jsonify({"error": "Conversation not found"}), 404
        else:
            # Create new conversation
            conversation = Conversation(user_id)
            conversation_data = conversation.to_dict()
            conversation_id = firebase_service.save_conversation(conversation_data)
            conversation_data['id'] = conversation_id
        
        # Add user message to conversation
        conversation_data['messages'].append({
            "content": message,
            "role": "user",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Generate AI response
        logger.info("🤖 Generating AI response with Gemini...")
        ai_response = gemini_service.generate_tasks_from_message(message, user_context)
        logger.info(f"✅ AI response generated: {len(ai_response.get('tasks', []))} tasks found")

        # Log suggestions for debugging
        suggestions = ai_response.get('suggestions', [])
        logger.info(f"💡 Suggestions in response: {len(suggestions)}")
        if suggestions:
            for idx, suggestion in enumerate(suggestions):
                logger.info(f"   💡 Suggestion {idx+1}: {suggestion.get('title', 'No title')} ({suggestion.get('type', 'unknown')})")
        else:
            logger.warning("⚠️ No suggestions returned by Gemini for text message")
        
        # Extract detected language for localization
        detected_language = ai_response.get('detected_language', 'en')
        logger.info(f"🌍 Language detected by Gemini: {detected_language}")
        
        # Apply localization to the response if needed
        localization_service = getattr(current_app, 'localization_service', None)
        if localization_service and detected_language != 'en' and ai_response.get('tasks'):
            try:
                ai_response['tasks'] = localization_service.localize_task_list(
                    ai_response['tasks'], detected_language
                )
                logger.info(f"🌍 Applied {detected_language} localization to Gemini response")
            except Exception as e:
                logger.warning(f"⚠️ Failed to localize Gemini response: {e}")
        
        # Add AI response to conversation
        conversation_data['messages'].append({
            "content": ai_response,
            "role": "assistant",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Update conversation in Firebase
        logger.info("💾 Updating conversation in Firebase...")
        firebase_service.update_conversation(conversation_id, {
            "messages": conversation_data['messages'],
            "updated_at": datetime.utcnow()
        })
        
        logger.info(f"🎉 Chat message processed successfully for user {user_id}")
        return jsonify({
            "conversation_id": conversation_id,
            "response": ai_response,
            "message_count": len(conversation_data['messages'])
        })
        
    except Exception as e:
        logger.error(f"❌ Error processing chat message: {str(e)}")
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/conversations/<user_id>', methods=['GET'])
@require_auth
def get_conversations(user_id):
    try:
        # Security: Ensure user can only access their own conversations
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized: Cannot access another user's conversations"}), 403
            
        firebase_service = current_app.firebase_service
        conversations = firebase_service.get_user_conversations(user_id)
        
        return jsonify({"conversations": conversations})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/conversation/<conversation_id>', methods=['GET'])
@require_auth
def get_conversation(conversation_id):
    try:
        firebase_service = current_app.firebase_service
        conversation = firebase_service.get_conversation_by_id(conversation_id)
        
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
        
        # Security: Ensure user can only access their own conversations
        if conversation.get('user_id') != request.user_id:
            return jsonify({"error": "Unauthorized: Cannot access another user's conversation"}), 403
        
        return jsonify({"conversation": conversation})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/conversations', methods=['POST'])
@require_auth
def create_conversation():
    try:
        data = request.get_json()
        title = data.get('title', 'New Conversation')
        
        # Security: Use authenticated user ID instead of request body
        user_id = request.user_id
        
        conversation = Conversation(user_id, title=title)
        conversation_data = conversation.to_dict()
        
        firebase_service = current_app.firebase_service
        conversation_id = firebase_service.save_conversation(conversation_data)
        conversation_data['id'] = conversation_id
        
        return jsonify({"conversation": conversation_data}), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/conversation/<conversation_id>', methods=['PUT'])
@require_auth
def update_conversation(conversation_id):
    try:
        data = request.get_json()
        
        firebase_service = current_app.firebase_service
        
        # Check if conversation exists
        conversation = firebase_service.get_conversation_by_id(conversation_id)
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
        
        # Security: Ensure user can only update their own conversations
        if conversation.get('user_id') != request.user_id:
            return jsonify({"error": "Unauthorized: Cannot update another user's conversation"}), 403
        
        # Update conversation
        update_data = {}
        if 'title' in data:
            update_data['title'] = data['title']
        
        update_data['updated_at'] = datetime.utcnow()
        
        firebase_service.update_conversation(conversation_id, update_data)
        
        # Return updated conversation
        updated_conversation = firebase_service.get_conversation_by_id(conversation_id)
        return jsonify({"conversation": updated_conversation})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/conversation/<conversation_id>', methods=['DELETE'])
@require_auth
def delete_conversation(conversation_id):
    try:
        firebase_service = current_app.firebase_service
        
        # Check if conversation exists
        conversation = firebase_service.get_conversation_by_id(conversation_id)
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
        
        # Security: Ensure user can only delete their own conversations
        if conversation.get('user_id') != request.user_id:
            return jsonify({"error": "Unauthorized: Cannot delete another user's conversation"}), 403
        
        # Delete conversation
        firebase_service.delete_conversation(conversation_id)
        
        return jsonify({"message": "Conversation deleted successfully"}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/conversations/<user_id>/search', methods=['GET'])
@require_auth
def search_conversations(user_id):
    try:
        # Security: Ensure user can only search their own conversations
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized: Cannot search another user's conversations"}), 403
            
        query = request.args.get('q', '')
        
        if not query:
            return jsonify({"error": "Search query is required"}), 400
        
        firebase_service = current_app.firebase_service
        conversations = firebase_service.search_user_conversations(user_id, query)
        
        return jsonify({"conversations": conversations})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/conversations/<user_id>/stats', methods=['GET'])
@require_auth
def get_conversation_stats(user_id):
    try:
        # Security: Ensure user can only access their own conversation stats
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized: Cannot access another user's conversation stats"}), 403
            
        firebase_service = current_app.firebase_service
        stats = firebase_service.get_conversation_stats(user_id)
        
        return jsonify({"stats": stats})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@chat_bp.route('/send-audio', methods=['POST'])
@require_auth
def send_audio_message():
    logger = get_logger()
    logger.info("🎤 Processing audio message...")
    
    try:
        # Check if audio file is present
        if 'audio' not in request.files:
            logger.error("❌ No audio file provided in request")
            return jsonify({"error": "No audio file provided"}), 400
        
        audio_file = request.files['audio']
        # Security: Use authenticated user ID instead of request form
        user_id = request.user_id
        conversation_id = request.form.get('conversation_id')
        
        logger.info(f"👤 User ID: {user_id}")
        logger.info(f"💬 Conversation ID: {conversation_id}")
        logger.info(f"📁 Audio file: {audio_file.filename}")
        
        if not user_id:
            logger.error("❌ Missing required field: user_id")
            return jsonify({"error": "user_id is required"}), 400
        
        if audio_file.filename == '':
            logger.error("❌ No audio file selected")
            return jsonify({"error": "No audio file selected"}), 400
        
        # Use concurrent request limiting and secure file handling
        with audio_request_limiter():
            with secure_temp_file(user_id) as audio_path:
                # Save audio file to temporary location
                logger.info(f"💾 Saving audio file to: {audio_path}")
                audio_file.save(audio_path)
                logger.info(f"✅ Audio file saved successfully")
                
                # Also save audio file permanently using audio storage service
                try:
                    from .audio_storage import store_audio_file_for_user
                    permanent_file_info = store_audio_file_for_user(
                        user_id=user_id,
                        audio_file_path=audio_path,
                        custom_name="voice_message"
                    )
                    logger.info(f"💾 Audio file permanently stored: {permanent_file_info['filename']}")
                except Exception as storage_error:
                    logger.warning(f"⚠️ Failed to permanently store audio file: {storage_error}")
                    # Continue processing even if permanent storage fails
                
                firebase_service = current_app.firebase_service
                gemini_service = current_app.gemini_service
                
                # Get user context and existing tasks for duplicate detection
                logger.info("🔍 Getting user context...")
                user_context = firebase_service.get_user_context(user_id)

                # Get user's active tasks for duplicate detection
                logger.info("🔍 Getting user's active tasks for duplicate detection...")
                try:
                    existing_tasks = firebase_service.get_user_tasks(user_id, status=['pending', 'approved'])
                    user_context['existing_tasks'] = [
                        {
                            'title': task.get('title', ''),
                            'description': task.get('description', ''),
                            'category': task.get('category', ''),
                            'id': task.get('id', '')
                        }
                        for task in existing_tasks[:10]  # Limit to recent 10 tasks for context
                    ]
                    logger.info(f"📋 Found {len(existing_tasks)} active tasks for duplicate detection")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to get existing tasks for duplicate detection: {e}")
                    user_context['existing_tasks'] = []
                
                # Get or create conversation
                if conversation_id:
                    # Load existing conversation
                    conversations = firebase_service.get_user_conversations(user_id)
                    conversation_data = next((c for c in conversations if c['id'] == conversation_id), None)
                    if not conversation_data:
                        return jsonify({"error": "Conversation not found"}), 404
                else:
                    # Create new conversation
                    conversation = Conversation(user_id)
                    conversation_data = conversation.to_dict()
                    conversation_id = firebase_service.save_conversation(conversation_data)
                    conversation_data['id'] = conversation_id
                
                # Process audio with Gemini
                logger.info("🤖 Processing audio with Gemini...")
                ai_response = gemini_service.generate_tasks_from_audio(audio_path, user_context)
                logger.info(f"✅ Audio processed: {len(ai_response.get('tasks', []))} tasks found")

                # Log suggestions for debugging
                suggestions = ai_response.get('suggestions', [])
                logger.info(f"💡 Suggestions in audio response: {len(suggestions)}")
                if suggestions:
                    for idx, suggestion in enumerate(suggestions):
                        logger.info(f"   💡 Suggestion {idx+1}: {suggestion.get('title', 'No title')} ({suggestion.get('type', 'unknown')})")
                else:
                    logger.warning("⚠️ No suggestions returned by Gemini for audio message")
                
                # Extract detected language for localization
                detected_language = ai_response.get('detected_language', 'en')
                logger.info(f"🌍 Language detected by Gemini from audio: {detected_language}")
                
                # Apply localization to the response if needed
                localization_service = getattr(current_app, 'localization_service', None)
                if localization_service and detected_language != 'en' and ai_response.get('tasks'):
                    try:
                        ai_response['tasks'] = localization_service.localize_task_list(
                            ai_response['tasks'], detected_language
                        )
                        logger.info(f"🌍 Applied {detected_language} localization to audio response")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to localize audio response: {e}")
                
                # Add placeholder for audio message in conversation
                conversation_data['messages'].append({
                    "content": "[Audio Message]",
                    "role": "user",
                    "timestamp": datetime.utcnow().isoformat(),
                    "type": "audio"
                })
                
                # Add AI response to conversation
                conversation_data['messages'].append({
                    "content": ai_response,
                    "role": "assistant",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                # Update conversation in Firebase
                logger.info("💾 Updating conversation in Firebase...")
                firebase_service.update_conversation(conversation_id, {
                    "messages": conversation_data['messages'],
                    "updated_at": datetime.utcnow()
                })
                
                logger.info(f"🎉 Audio message processed successfully for user {user_id}")
                
                # Extract the required fields for frontend compatibility
                transcription = ai_response.get('transcription', '')
                tasks = ai_response.get('tasks', [])
                confidence = 0.8  # Default confidence
                
                # Try to extract confidence from analysis if available
                if 'analysis' in ai_response and isinstance(ai_response['analysis'], dict):
                    analysis = ai_response['analysis']
                    if 'confidence' in analysis:
                        confidence = float(analysis['confidence'])
                
                return jsonify({
                    "conversation_id": conversation_id,
                    "response": ai_response,
                    "message_count": len(conversation_data['messages']),
                    # Frontend-compatible fields
                    "transcribed_text": transcription,
                    "tasks": tasks,
                    "confidence": confidence,
                    # Audio storage info (if available)
                    "audio_stored": True
                })
        
    except Exception as e:
        logger.error(f"❌ Error processing audio message: {str(e)}")
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/transcribe-audio', methods=['POST'])
@require_auth
def transcribe_audio():
    logger = get_logger()
    logger.info("🎤📝 Processing audio transcription request...")
    
    try:
        # Check if audio file is present
        if 'audio' not in request.files:
            logger.error("❌ No audio file provided in request")
            return jsonify({"error": "No audio file provided"}), 400
        
        audio_file = request.files['audio']
        # Security: Use authenticated user ID instead of request form
        user_id = request.user_id
        
        logger.info(f"👤 User ID: {user_id}")
        logger.info(f"📁 Audio file: {audio_file.filename}")
        
        if not user_id:
            logger.error("❌ Missing required field: user_id")
            return jsonify({"error": "user_id is required"}), 400
        
        if audio_file.filename == '':
            logger.error("❌ No audio file selected")
            return jsonify({"error": "No audio file selected"}), 400
        
        # Use concurrent request limiting and secure file handling
        with audio_request_limiter():
            with secure_temp_file(user_id) as audio_path:
                # Save audio file
                logger.info(f"💾 Saving audio file to: {audio_path}")
                audio_file.save(audio_path)
                logger.info(f"✅ Audio file saved successfully")
                
                gemini_service = current_app.gemini_service
                
                # Transcribe audio to text
                logger.info("🤖 Transcribing audio with Gemini...")
                transcribed_text = gemini_service.transcribe_audio(audio_path)
                logger.info(f"✅ Audio transcribed successfully: {len(transcribed_text)} characters")
                
                return jsonify({
                    "transcribed_text": transcribed_text,
                    "success": True
                })
        
    except Exception as e:
        logger.error(f"❌ Error processing audio transcription: {str(e)}")
        return jsonify({"error": str(e)}), 500