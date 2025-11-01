"""
Meeting Recorder Routes
Handles audio recording analysis, storage, and chat functionality for meetings/lectures
"""

from flask import Blueprint, request, jsonify, current_app
import logging
from datetime import datetime
import os
import json
import re

from utils.auth import require_auth
from prompts.gemini_prompts import MEETING_ANALYSIS_PROMPT, MEETING_CHAT_PROMPT

logger = logging.getLogger(__name__)

# Create blueprint
meetings_bp = Blueprint('meetings', __name__, url_prefix='/api/meetings')


@meetings_bp.route('/analyze', methods=['POST'])
@require_auth
def analyze_recording():
    """
    Analyze an audio recording using Gemini AI
    Expects multipart/form-data with audio file
    """
    try:
        # Get services from app context
        firebase_service = current_app.firebase_service
        gemini_service = current_app.gemini_service

        user_id = request.user_id
        logger.info(f"📊 Starting recording analysis for user: {user_id}")

        # Get audio file from request
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400

        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400

        # Read audio data
        audio_data = audio_file.read()
        duration = int(request.form.get('duration', 0))  # Duration in seconds

        logger.info(f"🎤 Processing audio file: {audio_file.filename}, duration: {duration}s")

        # Analyze with Gemini
        logger.info("🤖 Sending to Gemini for analysis...")
        current_date = datetime.now().strftime("%B %d, %Y")

        # Use Gemini to analyze the audio
        analysis_result = gemini_service.analyze_audio_recording(
            audio_data=audio_data,
            duration=duration,
            current_date=current_date
        )

        if not analysis_result.get('success'):
            logger.error(f"❌ Gemini analysis failed: {analysis_result.get('error')}")
            return jsonify({'error': 'AI analysis failed', 'details': analysis_result.get('error')}), 500

        # Extract analysis
        analysis = analysis_result.get('analysis', {})
        metadata = analysis.get('metadata', {})

        logger.info(f"✅ Analysis complete. Type: {metadata.get('detectedType')}, Title: {metadata.get('suggestedTitle')}")

        # Save to Firestore
        recording_data = {
            'userId': user_id,
            'title': metadata.get('suggestedTitle', 'Untitled Recording'),
            'date': datetime.now().isoformat(),
            'duration': duration,
            'type': metadata.get('detectedType', 'personal'),
            'aiDetected': metadata.get('confidence', 0) > 0.7,
            'language': metadata.get('language', 'en'),
            'summary': analysis.get('summary', {}),
            'sentiment': analysis.get('sentiment'),
            'transcript': analysis.get('transcript', []),
            'actionItems': analysis.get('actionItems', []),
            'keyPoints': analysis.get('keyPoints', []),
            'decisions': analysis.get('decisions', []),
            'topics': analysis.get('topics', []),
            'questions': analysis.get('questions', []),
            'nextSteps': analysis.get('nextSteps', []),
            'createdAt': datetime.now().isoformat(),
            'updatedAt': datetime.now().isoformat()
        }

        # Save recording to Firestore
        recording_id = firebase_service.save_recording(recording_data)
        recording_data['id'] = recording_id

        logger.info(f"💾 Recording saved with ID: {recording_id}")

        return jsonify({
            'success': True,
            'recordingId': recording_id,
            'recording': recording_data
        }), 200

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"❌ Error analyzing recording: {str(e)}")
        logger.error(f"Full traceback:\n{error_details}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e),
            'traceback': error_details
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
