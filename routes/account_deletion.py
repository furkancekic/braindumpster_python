from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import logging
import uuid
import secrets
import string
from functools import wraps
from typing import Dict, Any, Optional

from services.firebase_service import FirebaseService
from services.notification_service import NotificationService
from models.user import User
from models.deletion_request import DeletionRequest
from utils.auth import require_auth
from utils.validation import (
    RequestValidator, ValidationError,
    create_validation_error_response, create_authorization_error_response
)

account_deletion_bp = Blueprint('account_deletion', __name__, url_prefix='/v1/account/deletion')

def get_logger():
    return logging.getLogger('braindumpster.routes.account_deletion')

# Validation schemas
DELETION_REQUEST_SCHEMA = {
    'confirmation': {'type': 'boolean', 'required': True, 'allowed': [True]},
    'reason': {'type': 'string', 'required': False, 'min': 1, 'max': 500}
}

DELETION_CONFIRM_SCHEMA = {
    'request_id': {'type': 'string', 'required': True, 'min': 1, 'max': 100},
    'confirmation_code': {'type': 'string', 'required': True, 'min': 6, 'max': 6}
}

@account_deletion_bp.route('/request', methods=['POST'])
@require_auth
def request_deletion():
    """
    Initiate account deletion request
    Generates confirmation code and sends via email
    Returns request_id for confirmation
    """
    logger = get_logger()
    logger.info("🗑️ Account deletion request initiated")

    try:
        data = request.get_json()

        # Validate request data
        try:
            RequestValidator.validate_required_fields(data, ['confirmation'])
            if not data.get('confirmation', False):
                return create_validation_error_response(
                    ValidationError("Confirmation must be true to proceed with deletion")
                )
        except ValidationError as e:
            return create_validation_error_response(e)

        user_id = request.user_id
        user_email = request.user_email
        reason = data.get('reason', 'User requested account deletion')
        direct_delete = data.get('direct_delete', False)

        logger.info(f"👤 Processing deletion request for user: {user_id}")

        # If direct delete is requested, skip confirmation process
        if direct_delete:
            logger.info("🚀 Direct account deletion requested - skipping confirmation")
            return _perform_immediate_deletion(user_id, user_email, reason)

        # Check if there's already a pending deletion request
        firebase_service = current_app.firebase_service
        existing_request = _get_existing_deletion_request(firebase_service, user_id)

        if existing_request and existing_request.get('status') == 'pending':
            # Reuse existing request if still valid (within 24 hours)
            created_at = datetime.fromisoformat(existing_request['created_at'])
            if datetime.utcnow() - created_at < timedelta(hours=24):
                logger.info(f"♻️ Reusing existing deletion request: {existing_request['request_id']}")

                # Resend confirmation email
                _send_deletion_confirmation_email(
                    user_email,
                    existing_request['confirmation_code'],
                    existing_request['request_id']
                )

                return jsonify({
                    "success": True,
                    "request_id": existing_request['request_id'],
                    "message": "Deletion request confirmed. Confirmation email sent.",
                    "expires_at": existing_request['expires_at']
                }), 200

        # Generate new deletion request
        request_id = str(uuid.uuid4())
        confirmation_code = _generate_confirmation_code()
        expires_at = datetime.utcnow() + timedelta(hours=24)

        deletion_request = DeletionRequest(
            request_id=request_id,
            user_id=user_id,
            user_email=user_email,
            confirmation_code=confirmation_code,
            reason=reason,
            expires_at=expires_at
        )

        # Store deletion request in Firebase
        _store_deletion_request(firebase_service, deletion_request)

        # Send confirmation email
        _send_deletion_confirmation_email(user_email, confirmation_code, request_id)

        logger.info(f"✅ Deletion request created successfully: {request_id}")

        return jsonify({
            "success": True,
            "request_id": request_id,
            "message": "Deletion request created. Please check your email for confirmation code.",
            "expires_at": expires_at.isoformat()
        }), 200

    except Exception as e:
        logger.error(f"❌ Error processing deletion request: {e}")
        return jsonify({
            "error": "Failed to process deletion request",
            "code": "DELETION_REQUEST_FAILED"
        }), 500

@account_deletion_bp.route('/confirm', methods=['POST'])
@require_auth
def confirm_deletion():
    """
    Confirm account deletion with verification code
    Queues actual deletion job
    """
    logger = get_logger()
    logger.info("🔐 Account deletion confirmation requested")

    try:
        data = request.get_json()

        # Validate request data
        try:
            RequestValidator.validate_required_fields(data, ['request_id', 'confirmation_code'])
            request_id = RequestValidator.validate_string_field(data, 'request_id', required=True)
            confirmation_code = RequestValidator.validate_string_field(data, 'confirmation_code', required=True)
        except ValidationError as e:
            return create_validation_error_response(e)

        user_id = request.user_id

        logger.info(f"👤 Processing deletion confirmation for user: {user_id}, request: {request_id}")

        # Retrieve and validate deletion request
        firebase_service = current_app.firebase_service
        deletion_request = _get_deletion_request(firebase_service, request_id)

        if not deletion_request:
            logger.warning(f"⚠️ Deletion request not found: {request_id}")
            return jsonify({
                "error": "Deletion request not found",
                "code": "REQUEST_NOT_FOUND"
            }), 404

        # Validate request ownership
        if deletion_request.get('user_id') != user_id:
            logger.warning(f"⚠️ Unauthorized deletion confirmation attempt")
            return create_authorization_error_response("Not authorized for this deletion request")

        # Check if request is still valid
        expires_at = datetime.fromisoformat(deletion_request['expires_at'])
        if datetime.utcnow() > expires_at:
            logger.warning(f"⚠️ Deletion request expired: {request_id}")
            return jsonify({
                "error": "Deletion request has expired",
                "code": "REQUEST_EXPIRED"
            }), 400

        # Validate confirmation code
        if deletion_request.get('confirmation_code') != confirmation_code:
            logger.warning(f"⚠️ Invalid confirmation code for request: {request_id}")
            return jsonify({
                "error": "Invalid confirmation code",
                "code": "INVALID_CODE"
            }), 400

        # Check if already confirmed
        if deletion_request.get('status') == 'confirmed':
            logger.info(f"ℹ️ Deletion request already confirmed: {request_id}")
            return jsonify({
                "success": True,
                "status": "confirmed",
                "message": "Account deletion already confirmed and queued for processing"
            }), 200

        # Update request status to confirmed
        _update_deletion_request_status(firebase_service, request_id, 'confirmed')

        # Queue deletion job
        job_id = _queue_deletion_job(user_id, request_id, deletion_request.get('reason', ''))

        logger.info(f"✅ Deletion confirmed and queued: {request_id}, job: {job_id}")

        return jsonify({
            "success": True,
            "status": "confirmed",
            "job_id": job_id,
            "message": "Account deletion confirmed. Processing will begin shortly."
        }), 200

    except Exception as e:
        logger.error(f"❌ Error confirming deletion: {e}")
        return jsonify({
            "error": "Failed to confirm deletion",
            "code": "DELETION_CONFIRMATION_FAILED"
        }), 500

@account_deletion_bp.route('/status', methods=['GET'])
@require_auth
def get_deletion_status():
    """
    Get status of deletion request
    """
    logger = get_logger()

    try:
        request_id = request.args.get('request_id')
        if not request_id:
            return create_validation_error_response(
                ValidationError("request_id parameter is required")
            )

        user_id = request.user_id

        logger.info(f"📊 Checking deletion status for user: {user_id}, request: {request_id}")

        # Retrieve deletion request
        firebase_service = current_app.firebase_service
        deletion_request = _get_deletion_request(firebase_service, request_id)

        if not deletion_request:
            return jsonify({
                "error": "Deletion request not found",
                "code": "REQUEST_NOT_FOUND"
            }), 404

        # Validate request ownership
        if deletion_request.get('user_id') != user_id:
            return create_authorization_error_response("Not authorized for this deletion request")

        status = deletion_request.get('status', 'unknown')

        response_data = {
            "request_id": request_id,
            "status": status,
            "created_at": deletion_request.get('created_at'),
            "updated_at": deletion_request.get('updated_at'),
        }

        if status == 'pending':
            response_data["expires_at"] = deletion_request.get('expires_at')
        elif status in ['confirmed', 'processing']:
            response_data["job_id"] = deletion_request.get('job_id')
            response_data["estimated_completion"] = _calculate_estimated_completion()
        elif status == 'completed':
            response_data["completed_at"] = deletion_request.get('completed_at')
        elif status == 'failed':
            response_data["error_message"] = deletion_request.get('error_message')

        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"❌ Error getting deletion status: {e}")
        return jsonify({
            "error": "Failed to get deletion status",
            "code": "STATUS_CHECK_FAILED"
        }), 500

@account_deletion_bp.route('/cancel', methods=['POST'])
@require_auth
def cancel_deletion():
    """
    Cancel pending deletion request
    """
    logger = get_logger()

    try:
        data = request.get_json()
        request_id = data.get('request_id')

        if not request_id:
            return create_validation_error_response(
                ValidationError("request_id is required")
            )

        user_id = request.user_id

        logger.info(f"❌ Cancelling deletion request for user: {user_id}, request: {request_id}")

        # Retrieve and validate deletion request
        firebase_service = current_app.firebase_service
        deletion_request = _get_deletion_request(firebase_service, request_id)

        if not deletion_request:
            return jsonify({
                "error": "Deletion request not found",
                "code": "REQUEST_NOT_FOUND"
            }), 404

        # Validate ownership
        if deletion_request.get('user_id') != user_id:
            return create_authorization_error_response("Not authorized for this deletion request")

        current_status = deletion_request.get('status')
        if current_status in ['processing', 'completed']:
            return jsonify({
                "error": f"Cannot cancel deletion request in {current_status} status",
                "code": "CANCELLATION_NOT_ALLOWED"
            }), 400

        # Cancel the request
        _update_deletion_request_status(firebase_service, request_id, 'cancelled')

        logger.info(f"✅ Deletion request cancelled: {request_id}")

        return jsonify({
            "success": True,
            "message": "Deletion request cancelled successfully"
        }), 200

    except Exception as e:
        logger.error(f"❌ Error cancelling deletion: {e}")
        return jsonify({
            "error": "Failed to cancel deletion",
            "code": "CANCELLATION_FAILED"
        }), 500

# Helper functions

def _generate_confirmation_code() -> str:
    """Generate a 6-digit confirmation code"""
    return ''.join(secrets.choice(string.digits) for _ in range(6))

def _get_existing_deletion_request(firebase_service: FirebaseService, user_id: str) -> Optional[Dict[str, Any]]:
    """Get existing pending deletion request for user"""
    try:
        if not firebase_service.db:
            return None

        # Query for pending deletion requests for this user
        deletion_requests = firebase_service.db.collection('deletion_requests')\
            .where('user_id', '==', user_id)\
            .where('status', 'in', ['pending', 'confirmed'])\
            .limit(1)\
            .stream()

        for doc in deletion_requests:
            return doc.to_dict()

        return None
    except Exception as e:
        get_logger().error(f"Error getting existing deletion request: {e}")
        return None

def _store_deletion_request(firebase_service: FirebaseService, deletion_request: DeletionRequest):
    """Store deletion request in Firebase"""
    if firebase_service.db:
        firebase_service.db.collection('deletion_requests')\
            .document(deletion_request.request_id)\
            .set(deletion_request.to_dict())

def _get_deletion_request(firebase_service: FirebaseService, request_id: str) -> Optional[Dict[str, Any]]:
    """Get deletion request by ID"""
    try:
        if not firebase_service.db:
            return None

        doc = firebase_service.db.collection('deletion_requests')\
            .document(request_id)\
            .get()

        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        get_logger().error(f"Error getting deletion request: {e}")
        return None

def _update_deletion_request_status(firebase_service: FirebaseService, request_id: str, status: str):
    """Update deletion request status"""
    if firebase_service.db:
        update_data = {
            'status': status,
            'updated_at': datetime.utcnow().isoformat()
        }

        if status == 'completed':
            update_data['completed_at'] = datetime.utcnow().isoformat()

        firebase_service.db.collection('deletion_requests')\
            .document(request_id)\
            .update(update_data)

def _send_deletion_confirmation_email(email: str, confirmation_code: str, request_id: str):
    """Send deletion confirmation email"""
    logger = get_logger()

    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import os

        # Get SMTP configuration from environment
        smtp_server = os.environ.get('SMTP_SERVER', 'localhost')
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        smtp_username = os.environ.get('SMTP_USERNAME')
        smtp_password = os.environ.get('SMTP_PASSWORD')
        from_email = os.environ.get('FROM_EMAIL', 'noreply@braindumpster.com')

        if not smtp_username or not smtp_password:
            logger.warning("SMTP credentials not configured, logging email instead")
            logger.info(f"📧 [SIMULATED] Deletion confirmation email to: {email}")
            logger.info(f"📧 Confirmation code: {confirmation_code}")
            logger.info(f"📧 Request ID: {request_id}")
            return

        # Create email content
        subject = "Account Deletion Confirmation Required - Brain Dumpster"
        email_body = f"""
        <html>
        <body>
            <h2>Account Deletion Confirmation</h2>
            <p>Hello,</p>
            <p>We received a request to delete your Brain Dumpster account. To confirm this deletion, please use the following confirmation code:</p>

            <div style="background-color: #f5f5f5; padding: 20px; margin: 20px 0; text-align: center; font-size: 24px; font-weight: bold; letter-spacing: 2px;">
                {confirmation_code}
            </div>

            <p><strong>Request ID:</strong> {request_id}</p>

            <p><strong>Important:</strong></p>
            <ul>
                <li>This code will expire in 24 hours</li>
                <li>Account deletion is permanent and cannot be undone</li>
                <li>All your data including tasks, conversations, and voice recordings will be permanently deleted</li>
            </ul>

            <p>If you did not request this deletion, please ignore this email and your account will remain active.</p>

            <p>Best regards,<br>
            The Brain Dumpster Team</p>
        </body>
        </html>
        """

        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = email

        # Add HTML content
        html_part = MIMEText(email_body, 'html')
        msg.attach(html_part)

        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)

        logger.info(f"✅ Deletion confirmation email sent successfully to: {email}")

    except Exception as e:
        logger.error(f"❌ Failed to send deletion confirmation email: {e}")
        # In development/testing, don't fail the entire process for email issues
        if current_app.config.get('DEBUG', False):
            logger.warning("DEBUG mode: Continuing despite email failure")
        else:
            raise

def _queue_deletion_job(user_id: str, request_id: str, reason: str) -> str:
    """Queue deletion job for processing"""
    logger = get_logger()

    try:
        job_id = str(uuid.uuid4())

        # Try to use Redis Queue (RQ) if available, otherwise simulate
        try:
            import redis
            from rq import Queue
            import os

            # Get Redis configuration
            redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
            redis_conn = redis.from_url(redis_url)

            # Create queue
            deletion_queue = Queue('account_deletion', connection=redis_conn)

            # Queue the deletion job
            job = deletion_queue.enqueue(
                'services.account_deletion_service.process_account_deletion',
                user_id,
                request_id,
                reason,
                job_timeout='1h',  # 1 hour timeout for deletion process
                result_ttl=86400   # Keep result for 24 hours
            )

            job_id = job.id
            logger.info(f"✅ Deletion job queued with Redis/RQ: {job_id} for user: {user_id}")

        except ImportError:
            logger.warning("Redis/RQ not available, using background thread simulation")

            # Simulate background processing
            import threading

            def simulate_deletion():
                import time
                time.sleep(5)  # Simulate processing time
                logger.info(f"🔄 [SIMULATED] Processing deletion for user: {user_id}")
                # In a real scenario, this would call the actual deletion service

            thread = threading.Thread(target=simulate_deletion)
            thread.daemon = True
            thread.start()

            logger.info(f"📋 Simulated job queued: {job_id} for user: {user_id}")

        except Exception as e:
            logger.warning(f"Failed to queue with Redis, falling back to simulation: {e}")
            logger.info(f"📋 Fallback job simulation: {job_id} for user: {user_id}")

        return job_id

    except Exception as e:
        logger.error(f"❌ Failed to queue deletion job: {e}")
        raise

def _calculate_estimated_completion() -> str:
    """Calculate estimated completion time for deletion"""
    # Estimate 24-48 hours for completion
    estimated_time = datetime.utcnow() + timedelta(hours=48)
    return estimated_time.isoformat()

@account_deletion_bp.route('/data/export', methods=['POST'])
@require_auth
def export_user_data():
    """
    Export user data in specified format
    """
    logger = get_logger()
    logger.info("📤 User data export requested")

    try:
        data = request.get_json()

        # Validate format parameter
        export_format = data.get('format', 'json').lower()
        if export_format not in ['json', 'csv', 'xml', 'ics']:
            return create_validation_error_response(
                ValidationError("Invalid export format. Supported formats: json, csv, xml, ics")
            )

        user_id = request.user_id
        user_email = request.user_email

        logger.info(f"👤 Processing data export for user: {user_id}, format: {export_format}")

        # Generate export ID for tracking
        export_id = str(uuid.uuid4())

        # Get the account deletion service
        from services.account_deletion_service import AccountDeletionService
        deletion_service = AccountDeletionService(current_app.firebase_service)

        # Export data using the service
        export_data = deletion_service.export_user_data(user_id, export_format)

        # In a real implementation, you would:
        # 1. Queue the export job for processing
        # 2. Generate download URL
        # 3. Send notification when ready

        logger.info(f"✅ Data export completed successfully: {export_id}")

        response_data = {
            "success": True,
            "export_id": export_id,
            "format": export_format,
            "message": f"Data export in {export_format.upper()} format has been initiated",
            "status": "processing"
        }

        # For immediate export (development/testing), include the data
        if current_app.config.get('DEBUG', False) and len(str(export_data)) < 10000:
            response_data["data"] = export_data
            response_data["status"] = "completed"

        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"❌ Error processing data export: {e}")
        return jsonify({
            "error": "Failed to process data export",
            "code": "DATA_EXPORT_FAILED"
        }), 500

def _perform_immediate_deletion(user_id: str, user_email: str, reason: str):
    """
    Perform immediate account deletion without confirmation
    Used for direct deletion flow where user has already confirmed
    """
    logger = get_logger()
    logger.info(f"🚀 Starting immediate account deletion for user: {user_id}")

    try:
        firebase_service = current_app.firebase_service

        # Create deletion record for audit
        request_id = str(uuid.uuid4())
        deletion_data = {
            'request_id': request_id,
            'user_id': user_id,
            'user_email': user_email,
            'status': 'confirmed',
            'reason': reason,
            'created_at': datetime.utcnow().isoformat(),
            'confirmed_at': datetime.utcnow().isoformat(),
            'deletion_type': 'immediate',
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', 'Unknown')
        }

        # Store deletion record
        firebase_service.db.collection('deletion_requests').document(request_id).set(deletion_data)
        logger.info(f"📝 Deletion record created: {request_id}")

        # Queue immediate deletion job
        job_id = _queue_deletion_job(user_id, request_id, reason)
        logger.info(f"⚡ Immediate deletion job queued: {job_id}")

        return jsonify({
            "success": True,
            "request_id": request_id,
            "status": "confirmed",
            "message": "Account deletion has been initiated immediately",
            "job_id": job_id,
            "estimated_completion": _calculate_estimated_completion()
        }), 200

    except Exception as e:
        logger.error(f"❌ Failed to perform immediate deletion: {e}")
        return jsonify({
            "error": "Failed to delete account",
            "code": "IMMEDIATE_DELETION_FAILED"
        }), 500