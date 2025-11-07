"""
Meeting Recorder Routes
Handles audio recording analysis, storage, and chat functionality for meetings/lectures
"""

from flask import Blueprint, request, jsonify, current_app, copy_current_request_context
import logging
from datetime import datetime
import os
import json
import re
import threading

from utils.auth import require_auth
from prompts.gemini_prompts import MEETING_ANALYSIS_PROMPT, MEETING_CHAT_PROMPT

logger = logging.getLogger(__name__)

# Create blueprint
meetings_bp = Blueprint('meetings', __name__, url_prefix='/api/meetings')


def _process_audio_in_background(recording_id, audio_data, duration, mime_type, user_id):
    """
    Background task to process audio with Gemini AI
    This runs in a separate thread to avoid blocking the HTTP response
    """
    try:
        from datetime import timezone
        from flask import current_app

        logger.info(f"🔄 Background processing started for recording: {recording_id}")

        # Get services from app context
        firebase_service = current_app.firebase_service
        gemini_service = current_app.gemini_service

        current_date = datetime.now().strftime("%B %d, %Y")

        # Analyze with Gemini
        logger.info(f"🤖 Sending to Gemini for analysis (recording: {recording_id})...")
        analysis_result = gemini_service.analyze_audio_recording(
            audio_data=audio_data,
            duration=duration,
            current_date=current_date,
            mime_type=mime_type
        )

        if not analysis_result.get('success'):
            logger.error(f"❌ Gemini analysis failed for recording {recording_id}: {analysis_result.get('error')}")
            # Update recording status to failed
            firebase_service.update_recording(recording_id, {
                'status': 'failed',
                'error': analysis_result.get('error', 'AI analysis failed'),
                'updatedAt': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
            }, user_id)
            return

        # Extract analysis
        analysis = analysis_result.get('analysis', {})
        metadata = analysis.get('metadata', {})

        logger.info(f"✅ Analysis complete for {recording_id}. Type: {metadata.get('detectedType')}, Title: {metadata.get('suggestedTitle')}")

        # Ensure summary has required fields
        summary = analysis.get('summary', {})
        if not summary or not summary.get('brief'):
            summary = {
                'brief': 'Recording analyzed',
                'detailed': 'Audio recording has been processed and analyzed.',
                'keyTakeaways': []
            }

        # Update recording with full analysis
        now = datetime.now(timezone.utc).replace(microsecond=0)
        updates = {
            'status': 'completed',
            'title': metadata.get('suggestedTitle', 'Untitled Recording'),
            'type': metadata.get('detectedType', 'personal'),
            'aiDetected': metadata.get('confidence', 0) > 0.7,
            'language': metadata.get('language', 'en'),
            'summary': summary,
            'sentiment': analysis.get('sentiment'),
            'transcript': analysis.get('transcript', []),
            'actionItems': analysis.get('actionItems', []),
            'keyPoints': analysis.get('keyPoints', []),
            'decisions': analysis.get('decisions', []),
            'topics': analysis.get('topics', []),
            'questions': analysis.get('questions', []),
            'nextSteps': analysis.get('nextSteps', []),
            'updatedAt': now.isoformat().replace('+00:00', 'Z')
        }

        firebase_service.update_recording(recording_id, updates, user_id)

        logger.info(f"💾 Recording {recording_id} updated with complete analysis")
        logger.info(f"   Key Points: {len(updates.get('keyPoints', []))}")
        logger.info(f"   Transcript: {len(updates.get('transcript', []))} segments")

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"❌ Error in background processing for recording {recording_id}: {str(e)}")
        logger.error(f"Full traceback:\n{error_details}")

        # Update recording status to failed
        try:
            firebase_service = current_app.firebase_service
            firebase_service.update_recording(recording_id, {
                'status': 'failed',
                'error': str(e),
                'updatedAt': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
            }, user_id)
        except Exception as update_error:
            logger.error(f"❌ Failed to update recording status: {update_error}")


@meetings_bp.route('/analyze', methods=['POST'])
@require_auth
def analyze_recording():
    """
    Analyze an audio recording using Gemini AI (ASYNC)
    Immediately returns recording ID with status='processing'
    Analysis happens in background and updates recording when complete

    Expects multipart/form-data with audio file
    """
    try:
        # Get services from app context
        firebase_service = current_app.firebase_service

        user_id = request.user_id
        logger.info(f"📊 Starting async recording analysis for user: {user_id}")

        # Get audio file from request
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400

        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400

        # Read audio data
        audio_data = audio_file.read()
        duration = int(request.form.get('duration', 0))  # Duration in seconds

        # Check file size
        file_size_mb = len(audio_data) / (1024 * 1024)
        if file_size_mb > 150:
            logger.warning(f"⚠️ File too large: {file_size_mb:.2f} MB")
            return jsonify({
                'error': 'File too large',
                'details': f'Audio file is {file_size_mb:.1f} MB. Maximum allowed size is 150 MB.'
            }), 413

        # Detect MIME type from filename
        filename = audio_file.filename.lower()
        if filename.endswith('.mp3'):
            mime_type = 'audio/mpeg'
        elif filename.endswith('.m4a'):
            mime_type = 'audio/mp4'
        elif filename.endswith('.wav'):
            mime_type = 'audio/wav'
        elif filename.endswith('.aac'):
            mime_type = 'audio/aac'
        else:
            mime_type = 'audio/mp4'  # Default to m4a

        logger.info(f"🎤 Processing audio file: {audio_file.filename}, size: {file_size_mb:.2f} MB, duration: {duration}s")

        # Create initial recording with 'processing' status
        from datetime import timezone
        now = datetime.now(timezone.utc).replace(microsecond=0)

        initial_recording = {
            'userId': user_id,
            'title': 'Processing...',
            'date': now.isoformat().replace('+00:00', 'Z'),
            'duration': duration,
            'type': 'personal',
            'status': 'processing',
            'language': 'en',
            'summary': {
                'brief': 'Recording is being analyzed...',
                'detailed': 'Please wait while we process your audio recording.',
                'keyTakeaways': []
            },
            'createdAt': now.isoformat().replace('+00:00', 'Z'),
            'updatedAt': now.isoformat().replace('+00:00', 'Z')
        }

        # Save initial recording to Firestore
        logger.info(f"📝 Saving initial recording with status='processing'...")
        recording_id = firebase_service.save_recording(initial_recording)
        initial_recording['id'] = recording_id

        logger.info(f"💾 Recording created with ID: {recording_id}, status: processing")

        # Start background processing with Flask app context
        @copy_current_request_context
        def process_with_context():
            _process_audio_in_background(recording_id, audio_data, duration, mime_type, user_id)

        thread = threading.Thread(target=process_with_context)
        thread.daemon = True  # Daemon thread will be killed when main thread exits
        thread.start()

        logger.info(f"🚀 Background processing started for recording: {recording_id}")
        logger.info(f"📤 Returning immediate response to iOS...")

        # Return immediate response with processing status
        return jsonify({
            'success': True,
            'recordingId': recording_id,
            'recording': initial_recording,
            'message': 'Recording is being processed. Check status by fetching the recording.'
        }), 202  # 202 Accepted - request accepted for processing

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"❌ Error in analyze_recording: {str(e)}")
        logger.error(f"Full traceback:\n{error_details}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@meetings_bp.route('', methods=['GET'])
@require_auth
def get_recordings():
    """
    Get all recordings for the authenticated user
    Query params:
    - type: filter by type (meeting, lecture, personal)
    - limit: max number of recordings (default 50)
    """
    try:
        firebase_service = current_app.firebase_service

        user_id = request.user_id
        recording_type = request.args.get('type')
        limit = int(request.args.get('limit', 50))

        logger.info(f"📋 Fetching recordings for user: {user_id}, type: {recording_type}, limit: {limit}")

        recordings = firebase_service.get_user_recordings(user_id, recording_type, limit)

        logger.info(f"✅ Found {len(recordings)} recordings")

        return jsonify({
            'success': True,
            'recordings': recordings,
            'count': len(recordings)
        }), 200

    except Exception as e:
        logger.error(f"❌ Error fetching recordings: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500


@meetings_bp.route('/<recording_id>', methods=['GET'])
@require_auth
def get_recording(recording_id):
    """
    Get a single recording by ID
    """
    try:
        firebase_service = current_app.firebase_service

        user_id = request.user_id
        logger.info(f"📄 Fetching recording: {recording_id} for user: {user_id}")

        recording = firebase_service.get_recording(recording_id, user_id)

        if not recording:
            return jsonify({'error': 'Recording not found'}), 404

        return jsonify({
            'success': True,
            'recording': recording
        }), 200

    except Exception as e:
        logger.error(f"❌ Error fetching recording: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500


@meetings_bp.route('/<recording_id>', methods=['DELETE'])
@require_auth
def delete_recording(recording_id):
    """
    Delete a recording
    """
    try:
        firebase_service = current_app.firebase_service

        user_id = request.user_id
        logger.info(f"🗑️ Deleting recording: {recording_id} for user: {user_id}")

        # Verify ownership
        recording = firebase_service.get_recording(recording_id, user_id)
        if not recording:
            return jsonify({'error': 'Recording not found'}), 404

        # Delete from Firestore
        firebase_service.delete_recording(recording_id, user_id)

        logger.info(f"✅ Recording deleted: {recording_id}")

        return jsonify({
            'success': True,
            'message': 'Recording deleted successfully'
        }), 200

    except Exception as e:
        logger.error(f"❌ Error deleting recording: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500


@meetings_bp.route('/<recording_id>/chat', methods=['POST'])
@require_auth
def chat_with_recording(recording_id):
    """
    Ask AI questions about a recording
    Expects JSON: { "message": "question" }
    """
    try:
        firebase_service = current_app.firebase_service
        gemini_service = current_app.gemini_service

        user_id = request.user_id
        data = request.get_json()

        if not data or 'message' not in data:
            return jsonify({'error': 'Missing message in request'}), 400

        message = data['message']
        logger.info(f"💬 Chat question for recording {recording_id}: {message[:50]}...")

        # Get recording
        recording = firebase_service.get_recording(recording_id, user_id)
        if not recording:
            return jsonify({'error': 'Recording not found'}), 404

        # Prepare context for Gemini
        transcript_text = "\n".join([
            f"{seg.get('speaker', 'Unknown')} ({seg.get('timestamp', '00:00')}): {seg.get('text', '')}"
            for seg in recording.get('transcript', [])
        ])

        key_points_text = "\n".join([
            f"- {kp.get('timestamp', '00:00')}: {kp.get('point', '')}"
            for kp in recording.get('keyPoints', [])
        ])

        action_items_text = "\n".join([
            f"- {ai.get('task', '')} ({ai.get('assignee', 'Unknown')}, due: {ai.get('dueDate', 'TBD')})"
            for ai in recording.get('actionItems', [])
        ])

        decisions_text = "\n".join([
            f"- {d.get('decision', '')} (at {d.get('timestamp', '00:00')})"
            for d in recording.get('decisions', [])
        ])

        # Format duration
        duration_mins = recording.get('duration', 0) // 60
        duration_formatted = f"{duration_mins} minutes"

        # Create chat prompt
        prompt = MEETING_CHAT_PROMPT.format(
            title=recording.get('title', 'Untitled'),
            duration=duration_formatted,
            recording_type=recording.get('type', 'unknown'),
            transcript=transcript_text or "No transcript available",
            key_points=key_points_text or "No key points",
            action_items=action_items_text or "No action items",
            decisions=decisions_text or "No decisions recorded"
        )

        # Ask Gemini
        response = gemini_service.chat_about_recording(
            prompt=prompt,
            user_message=message
        )

        if not response.get('success'):
            logger.error(f"❌ Gemini chat failed: {response.get('error')}")
            return jsonify({'error': 'AI response failed', 'details': response.get('error')}), 500

        answer = response.get('response', 'I could not find an answer to that question in the recording.')

        logger.info(f"✅ Chat response generated: {answer[:100]}...")

        return jsonify({
            'success': True,
            'response': answer
        }), 200

    except Exception as e:
        logger.error(f"❌ Error in chat: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500
