"""
Audio Storage Management API Routes
Handles audio file storage, retrieval, and management via backend API
"""
import os
import tempfile
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app, send_file
from utils.auth import require_auth
import logging

logger = logging.getLogger(__name__)

audio_storage_bp = Blueprint('audio_storage', __name__)

# Audio storage configuration
AUDIO_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'voice_recordings')
MAX_FILES_PER_DAY = 50
MAX_FILE_AGE_DAYS = 30
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.aac', '.flac', '.ogg'}

def ensure_storage_directory():
    """Ensure audio storage directory exists"""
    if not os.path.exists(AUDIO_STORAGE_DIR):
        os.makedirs(AUDIO_STORAGE_DIR, exist_ok=True)
        logger.info(f"Created audio storage directory: {AUDIO_STORAGE_DIR}")

def get_user_audio_dir(user_id: str) -> str:
    """Get user-specific audio directory"""
    user_dir = os.path.join(AUDIO_STORAGE_DIR, user_id)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)
    return user_dir

def get_date_audio_dir(user_id: str, date: datetime) -> str:
    """Get date-specific audio directory for user"""
    user_dir = get_user_audio_dir(user_id)
    date_str = date.strftime('%Y-%m-%d')
    date_dir = os.path.join(user_dir, date_str)
    if not os.path.exists(date_dir):
        os.makedirs(date_dir, exist_ok=True)
    return date_dir

def is_audio_file(filename: str) -> bool:
    """Check if file is an audio file"""
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)

def cleanup_old_files(user_id: str):
    """Clean up old audio files beyond retention period"""
    try:
        user_dir = get_user_audio_dir(user_id)
        cutoff_date = datetime.now() - timedelta(days=MAX_FILE_AGE_DAYS)
        deleted_count = 0
        
        for date_folder in os.listdir(user_dir):
            date_path = os.path.join(user_dir, date_folder)
            if os.path.isdir(date_path):
                try:
                    folder_date = datetime.strptime(date_folder, '%Y-%m-%d')
                    if folder_date < cutoff_date:
                        # Delete entire date folder
                        import shutil
                        shutil.rmtree(date_path)
                        deleted_count += 1
                        logger.info(f"Deleted old audio folder: {date_folder}")
                except ValueError:
                    # Not a date folder, skip
                    continue
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old audio folders for user {user_id}")
            
    except Exception as e:
        logger.error(f"Failed to cleanup old files for user {user_id}: {e}")

def cleanup_daily_files(user_id: str, date: datetime):
    """Clean up daily files if we have too many"""
    try:
        date_dir = get_date_audio_dir(user_id, date)
        audio_files = [f for f in os.listdir(date_dir) if is_audio_file(f)]
        
        if len(audio_files) > MAX_FILES_PER_DAY:
            # Sort by creation time (oldest first)
            audio_files.sort(key=lambda f: os.path.getctime(os.path.join(date_dir, f)))
            
            # Delete oldest files
            files_to_delete = audio_files[:len(audio_files) - MAX_FILES_PER_DAY]
            for file_to_delete in files_to_delete:
                file_path = os.path.join(date_dir, file_to_delete)
                os.remove(file_path)
                logger.info(f"Deleted old audio file: {file_to_delete}")
                
    except Exception as e:
        logger.error(f"Failed to cleanup daily files for user {user_id}: {e}")

@audio_storage_bp.route('/store', methods=['POST'])
@require_auth
def store_audio_file():
    """Store audio file for user"""
    try:
        ensure_storage_directory()
        user_id = request.user_id
        
        # Check if audio file is present
        if 'audio' not in request.files:
            return jsonify({"error": "No audio file provided"}), 400
        
        audio_file = request.files['audio']
        custom_name = request.form.get('custom_name', 'recording')
        
        if audio_file.filename == '':
            return jsonify({"error": "No audio file selected"}), 400
        
        # Validate file size
        audio_file.seek(0, 2)  # Seek to end
        file_size = audio_file.tell()
        audio_file.seek(0)  # Reset to beginning
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({"error": f"File too large. Maximum size: {MAX_FILE_SIZE} bytes"}), 400
        
        if file_size < 1000:  # Less than 1KB
            return jsonify({"error": "File too small, might be corrupted"}), 400
        
        # Generate unique filename
        now = datetime.now()
        timestamp = now.strftime('%H%M%S')
        milliseconds = str(now.microsecond)[:3]
        
        original_ext = os.path.splitext(audio_file.filename)[1]
        if not original_ext:
            original_ext = '.aac'  # Default extension (AAC format only)
        
        filename = f"{custom_name}_{timestamp}_{milliseconds}{original_ext}"
        filename = secure_filename(filename)
        
        # Save file to date-specific directory
        date_dir = get_date_audio_dir(user_id, now)
        file_path = os.path.join(date_dir, filename)
        
        audio_file.save(file_path)
        
        # Clean up old files
        cleanup_old_files(user_id)
        cleanup_daily_files(user_id, now)
        
        # Get relative path for response
        relative_path = os.path.relpath(file_path, AUDIO_STORAGE_DIR)
        
        logger.info(f"✅ Audio file stored: {filename} ({file_size} bytes)")
        
        return jsonify({
            "success": True,
            "filename": filename,
            "file_path": relative_path,
            "file_size": file_size,
            "stored_at": now.isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to store audio file: {e}")
        return jsonify({"error": "Failed to store audio file"}), 500

@audio_storage_bp.route('/list', methods=['GET'])
@require_auth
def list_audio_files():
    """List audio files for user"""
    try:
        user_id = request.user_id
        date_str = request.args.get('date')  # Optional date filter (YYYY-MM-DD)
        limit = int(request.args.get('limit', 50))
        
        ensure_storage_directory()
        user_dir = get_user_audio_dir(user_id)
        
        audio_files = []
        
        if date_str:
            # List files for specific date
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d')
                date_dir = get_date_audio_dir(user_id, date)
                
                if os.path.exists(date_dir):
                    for filename in os.listdir(date_dir):
                        if is_audio_file(filename):
                            file_path = os.path.join(date_dir, filename)
                            file_stats = os.stat(file_path)
                            
                            audio_files.append({
                                "filename": filename,
                                "file_path": os.path.relpath(file_path, AUDIO_STORAGE_DIR),
                                "file_size": file_stats.st_size,
                                "created_at": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                                "modified_at": datetime.fromtimestamp(file_stats.st_mtime).isoformat()
                            })
            except ValueError:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        else:
            # List all files
            for date_folder in os.listdir(user_dir):
                date_path = os.path.join(user_dir, date_folder)
                if os.path.isdir(date_path):
                    for filename in os.listdir(date_path):
                        if is_audio_file(filename):
                            file_path = os.path.join(date_path, filename)
                            file_stats = os.stat(file_path)
                            
                            audio_files.append({
                                "filename": filename,
                                "file_path": os.path.relpath(file_path, AUDIO_STORAGE_DIR),
                                "file_size": file_stats.st_size,
                                "created_at": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                                "modified_at": datetime.fromtimestamp(file_stats.st_mtime).isoformat()
                            })
        
        # Sort by creation time (newest first)
        audio_files.sort(key=lambda f: f['created_at'], reverse=True)
        
        # Apply limit
        audio_files = audio_files[:limit]
        
        return jsonify({
            "success": True,
            "files": audio_files,
            "total_count": len(audio_files)
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to list audio files: {e}")
        return jsonify({"error": "Failed to list audio files"}), 500

@audio_storage_bp.route('/download/<path:file_path>', methods=['GET'])
@require_auth
def download_audio_file(file_path):
    """Download audio file"""
    try:
        user_id = request.user_id
        
        # Security: Ensure file belongs to the authenticated user
        full_path = os.path.join(AUDIO_STORAGE_DIR, file_path)
        user_dir = get_user_audio_dir(user_id)
        
        # Check if file path is within user directory
        if not full_path.startswith(user_dir):
            return jsonify({"error": "Access denied"}), 403
        
        if not os.path.exists(full_path):
            return jsonify({"error": "File not found"}), 404
        
        if not is_audio_file(full_path):
            return jsonify({"error": "Not an audio file"}), 400
        
        return send_file(full_path, as_attachment=True)
        
    except Exception as e:
        logger.error(f"❌ Failed to download audio file: {e}")
        return jsonify({"error": "Failed to download audio file"}), 500

@audio_storage_bp.route('/delete/<path:file_path>', methods=['DELETE'])
@require_auth
def delete_audio_file(file_path):
    """Delete audio file"""
    try:
        user_id = request.user_id
        
        # Security: Ensure file belongs to the authenticated user
        full_path = os.path.join(AUDIO_STORAGE_DIR, file_path)
        user_dir = get_user_audio_dir(user_id)
        
        # Check if file path is within user directory
        if not full_path.startswith(user_dir):
            return jsonify({"error": "Access denied"}), 403
        
        if not os.path.exists(full_path):
            return jsonify({"error": "File not found"}), 404
        
        # Delete file
        os.remove(full_path)
        
        # Clean up empty directories
        dir_path = os.path.dirname(full_path)
        if os.path.exists(dir_path) and not os.listdir(dir_path):
            os.rmdir(dir_path)
        
        logger.info(f"🗑️ Deleted audio file: {file_path}")
        
        return jsonify({
            "success": True,
            "message": "Audio file deleted successfully"
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to delete audio file: {e}")
        return jsonify({"error": "Failed to delete audio file"}), 500

@audio_storage_bp.route('/stats', methods=['GET'])
@require_auth
def get_storage_stats():
    """Get storage statistics for user"""
    try:
        user_id = request.user_id
        
        ensure_storage_directory()
        user_dir = get_user_audio_dir(user_id)
        
        total_files = 0
        total_size = 0
        files_by_date = {}
        
        for date_folder in os.listdir(user_dir):
            date_path = os.path.join(user_dir, date_folder)
            if os.path.isdir(date_path):
                date_files = [f for f in os.listdir(date_path) if is_audio_file(f)]
                date_size = sum(os.path.getsize(os.path.join(date_path, f)) for f in date_files)
                
                files_by_date[date_folder] = {
                    "file_count": len(date_files),
                    "total_size": date_size
                }
                
                total_files += len(date_files)
                total_size += date_size
        
        return jsonify({
            "success": True,
            "total_files": total_files,
            "total_size": total_size,
            "total_size_formatted": _format_bytes(total_size),
            "files_by_date": files_by_date,
            "retention_days": MAX_FILE_AGE_DAYS,
            "max_files_per_day": MAX_FILES_PER_DAY,
            "max_file_size": MAX_FILE_SIZE
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to get storage stats: {e}")
        return jsonify({"error": "Failed to get storage stats"}), 500

@audio_storage_bp.route('/clear', methods=['DELETE'])
@require_auth
def clear_all_audio_files():
    """Clear all audio files for user"""
    try:
        user_id = request.user_id
        
        user_dir = get_user_audio_dir(user_id)
        
        if os.path.exists(user_dir):
            import shutil
            shutil.rmtree(user_dir)
            logger.info(f"🧹 Cleared all audio files for user {user_id}")
        
        return jsonify({
            "success": True,
            "message": "All audio files cleared successfully"
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to clear audio files: {e}")
        return jsonify({"error": "Failed to clear audio files"}), 500

def store_audio_file_for_user(user_id: str, audio_file_path: str, custom_name: str = "recording") -> dict:
    """Store audio file for user (utility function for other routes)"""
    try:
        ensure_storage_directory()
        
        # Check if source file exists
        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"Source audio file not found: {audio_file_path}")
        
        # Get file size
        file_size = os.path.getsize(audio_file_path)
        
        if file_size > MAX_FILE_SIZE:
            raise ValueError(f"File too large: {file_size} bytes (max: {MAX_FILE_SIZE} bytes)")
        
        if file_size < 1000:  # Less than 1KB
            raise ValueError("File too small, might be corrupted")
        
        # Generate unique filename
        now = datetime.now()
        timestamp = now.strftime('%H%M%S')
        milliseconds = str(now.microsecond)[:3]
        
        # Detect file extension from source file
        original_ext = os.path.splitext(audio_file_path)[1]
        if not original_ext:
            original_ext = '.m4a'  # Default extension
        
        filename = f"{custom_name}_{timestamp}_{milliseconds}{original_ext}"
        filename = secure_filename(filename)
        
        # Save file to date-specific directory
        date_dir = get_date_audio_dir(user_id, now)
        destination_path = os.path.join(date_dir, filename)
        
        # Copy file to permanent storage
        import shutil
        shutil.copy2(audio_file_path, destination_path)
        
        # Clean up old files
        cleanup_old_files(user_id)
        cleanup_daily_files(user_id, now)
        
        # Get relative path for response
        relative_path = os.path.relpath(destination_path, AUDIO_STORAGE_DIR)
        
        logger.info(f"✅ Audio file stored permanently: {filename} ({file_size} bytes)")
        
        return {
            "success": True,
            "filename": filename,
            "file_path": relative_path,
            "file_size": file_size,
            "stored_at": now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to store audio file permanently: {e}")
        raise

def _format_bytes(bytes_value):
    """Format bytes to human readable string"""
    if bytes_value < 1024:
        return f"{bytes_value}B"
    elif bytes_value < 1024 * 1024:
        return f"{bytes_value / 1024:.1f}KB"
    elif bytes_value < 1024 * 1024 * 1024:
        return f"{bytes_value / (1024 * 1024):.1f}MB"
    else:
        return f"{bytes_value / (1024 * 1024 * 1024):.1f}GB"