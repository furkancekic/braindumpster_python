"""
App Store Server Notifications V2 Webhook Handler
Handles real-time subscription events from Apple
"""

from flask import Blueprint, request, jsonify, current_app
import json
import base64
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

apple_webhook_bp = Blueprint('apple_webhook', __name__, url_prefix='/api/webhooks')

@apple_webhook_bp.route('/apple', methods=['POST'])
def handle_apple_notification():
    """
    Handle App Store Server Notifications V2

    Notification Types:
    - SUBSCRIBED: New subscription
    - DID_RENEW: Subscription renewed
    - DID_FAIL_TO_RENEW: Renewal failed (billing issue)
    - DID_CHANGE_RENEWAL_STATUS: Auto-renew toggled
    - EXPIRED: Subscription expired
    - GRACE_PERIOD_EXPIRED: Grace period ended
    - REFUND: User refunded
    - REFUND_DECLINED: Refund request denied
    - CONSUMPTION_REQUEST: Apple requesting consumption data
    - PRICE_INCREASE: Subscription price increased
    - RENEWAL_EXTENDED: Subscription extended
    - REVOKE: Subscription revoked
    """
    try:
        # Get notification payload
        payload = request.get_json()

        if not payload:
            logger.error("❌ [Webhook] No payload received")
            return jsonify({"error": "No payload"}), 400

        logger.info("🔔 [Webhook] Received Apple notification")
        logger.info(f"   Full payload: {json.dumps(payload, indent=2)}")

        # Extract signedPayload (JWS)
        signed_payload = payload.get('signedPayload')

        if not signed_payload:
            logger.error("❌ [Webhook] No signedPayload found")
            return jsonify({"error": "No signedPayload"}), 400

        # Parse JWS (JSON Web Signature)
        # Format: header.payload.signature
        try:
            parts = signed_payload.split('.')
            if len(parts) != 3:
                raise ValueError("Invalid JWS format")

            # Decode payload (base64url)
            payload_part = parts[1]
            # Add padding if needed
            padding = 4 - len(payload_part) % 4
            if padding != 4:
                payload_part += '=' * padding

            decoded_payload = base64.urlsafe_b64decode(payload_part)
            notification_data = json.loads(decoded_payload)

            logger.info("✅ [Webhook] JWS decoded successfully")
            logger.info(f"   Notification data: {json.dumps(notification_data, indent=2)}")

        except Exception as decode_error:
            logger.error(f"❌ [Webhook] Failed to decode JWS: {decode_error}")
            return jsonify({"error": "Failed to decode JWS"}), 400

        # Extract notification type and data
        notification_type = notification_data.get('notificationType')
        subtype = notification_data.get('subtype')

        logger.info(f"📢 [Webhook] Notification Type: {notification_type}")
        logger.info(f"   Subtype: {subtype}")

        # Extract transaction data
        data = notification_data.get('data', {})
        signed_transaction_info = data.get('signedTransactionInfo')
        signed_renewal_info = data.get('signedRenewalInfo')

        # Decode transaction info
        transaction_data = None
        if signed_transaction_info:
            try:
                parts = signed_transaction_info.split('.')
                payload_part = parts[1]
                padding = 4 - len(payload_part) % 4
                if padding != 4:
                    payload_part += '=' * padding
                decoded = base64.urlsafe_b64decode(payload_part)
                transaction_data = json.loads(decoded)

                logger.info("✅ [Webhook] Transaction info decoded")
                logger.info(f"   Transaction: {json.dumps(transaction_data, indent=2)}")
            except Exception as e:
                logger.error(f"⚠️ [Webhook] Failed to decode transaction: {e}")

        # Decode renewal info
        renewal_data = None
        if signed_renewal_info:
            try:
                parts = signed_renewal_info.split('.')
                payload_part = parts[1]
                padding = 4 - len(payload_part) % 4
                if padding != 4:
                    payload_part += '=' * padding
                decoded = base64.urlsafe_b64decode(payload_part)
                renewal_data = json.loads(decoded)

                logger.info("✅ [Webhook] Renewal info decoded")
                logger.info(f"   Renewal: {json.dumps(renewal_data, indent=2)}")
            except Exception as e:
                logger.error(f"⚠️ [Webhook] Failed to decode renewal: {e}")

        # Handle different notification types
        if notification_type == 'SUBSCRIBED':
            handle_subscribed(notification_data, transaction_data, renewal_data)
        elif notification_type == 'DID_RENEW':
            handle_renewal(notification_data, transaction_data, renewal_data)
        elif notification_type == 'EXPIRED':
            handle_expiration(notification_data, transaction_data)
        elif notification_type == 'DID_FAIL_TO_RENEW':
            handle_renewal_failure(notification_data, transaction_data, renewal_data)
        elif notification_type == 'DID_CHANGE_RENEWAL_STATUS':
            handle_renewal_status_change(notification_data, renewal_data)
        elif notification_type == 'REFUND':
            handle_refund(notification_data, transaction_data)
        elif notification_type == 'GRACE_PERIOD_EXPIRED':
            handle_grace_period_expired(notification_data, transaction_data)
        else:
            logger.info(f"ℹ️  [Webhook] Unhandled notification type: {notification_type}")

        # Return success (Apple expects 200 OK)
        return jsonify({"status": "received"}), 200

    except Exception as e:
        logger.error(f"❌ [Webhook] Error processing notification: {e}")
        logger.exception(e)
        return jsonify({"error": str(e)}), 500


def handle_subscribed(notification_data, transaction_data, renewal_data):
    """Handle new subscription"""
    logger.info("🎉 [Webhook] Handling SUBSCRIBED event")

    if not transaction_data:
        logger.error("❌ [Webhook] No transaction data for SUBSCRIBED")
        return

    try:
        # Extract user and subscription info
        original_transaction_id = transaction_data.get('originalTransactionId')
        product_id = transaction_data.get('productId')
        expires_date_ms = transaction_data.get('expiresDate')

        # Update user's subscription in database
        update_subscription_status(
            original_transaction_id=original_transaction_id,
            product_id=product_id,
            is_active=True,
            expires_date_ms=expires_date_ms,
            will_renew=True
        )

        logger.info(f"✅ [Webhook] Subscription activated: {product_id}")

    except Exception as e:
        logger.error(f"❌ [Webhook] Failed to handle SUBSCRIBED: {e}")


def handle_renewal(notification_data, transaction_data, renewal_data):
    """Handle subscription renewal"""
    logger.info("🔄 [Webhook] Handling DID_RENEW event")

    if not transaction_data:
        logger.error("❌ [Webhook] No transaction data for DID_RENEW")
        return

    try:
        original_transaction_id = transaction_data.get('originalTransactionId')
        product_id = transaction_data.get('productId')
        expires_date_ms = transaction_data.get('expiresDate')

        # Update subscription
        update_subscription_status(
            original_transaction_id=original_transaction_id,
            product_id=product_id,
            is_active=True,
            expires_date_ms=expires_date_ms,
            will_renew=True
        )

        logger.info(f"✅ [Webhook] Subscription renewed: {product_id}")

    except Exception as e:
        logger.error(f"❌ [Webhook] Failed to handle DID_RENEW: {e}")


def handle_expiration(notification_data, transaction_data):
    """Handle subscription expiration"""
    logger.info("⏰ [Webhook] Handling EXPIRED event")

    if not transaction_data:
        logger.error("❌ [Webhook] No transaction data for EXPIRED")
        return

    try:
        original_transaction_id = transaction_data.get('originalTransactionId')
        product_id = transaction_data.get('productId')

        # Mark subscription as expired
        update_subscription_status(
            original_transaction_id=original_transaction_id,
            product_id=product_id,
            is_active=False,
            expires_date_ms=None,
            will_renew=False
        )

        logger.info(f"✅ [Webhook] Subscription expired: {product_id}")

    except Exception as e:
        logger.error(f"❌ [Webhook] Failed to handle EXPIRED: {e}")


def handle_renewal_failure(notification_data, transaction_data, renewal_data):
    """Handle renewal failure (billing issue)"""
    logger.info("⚠️ [Webhook] Handling DID_FAIL_TO_RENEW event")

    if not transaction_data:
        logger.error("❌ [Webhook] No transaction data for DID_FAIL_TO_RENEW")
        return

    try:
        original_transaction_id = transaction_data.get('originalTransactionId')
        product_id = transaction_data.get('productId')

        # Check grace period
        grace_period_expires_date = renewal_data.get('gracePeriodExpiresDate') if renewal_data else None

        if grace_period_expires_date:
            logger.info(f"   Grace period active until: {grace_period_expires_date}")
            # Keep subscription active during grace period
            update_subscription_status(
                original_transaction_id=original_transaction_id,
                product_id=product_id,
                is_active=True,
                expires_date_ms=grace_period_expires_date,
                will_renew=False,
                in_billing_retry=True
            )
        else:
            # No grace period, expire immediately
            update_subscription_status(
                original_transaction_id=original_transaction_id,
                product_id=product_id,
                is_active=False,
                expires_date_ms=None,
                will_renew=False
            )

        logger.info(f"✅ [Webhook] Renewal failure handled: {product_id}")

    except Exception as e:
        logger.error(f"❌ [Webhook] Failed to handle DID_FAIL_TO_RENEW: {e}")


def handle_renewal_status_change(notification_data, renewal_data):
    """Handle auto-renew status change"""
    logger.info("🔀 [Webhook] Handling DID_CHANGE_RENEWAL_STATUS event")

    if not renewal_data:
        logger.error("❌ [Webhook] No renewal data for DID_CHANGE_RENEWAL_STATUS")
        return

    try:
        original_transaction_id = renewal_data.get('originalTransactionId')
        auto_renew_status = renewal_data.get('autoRenewStatus')

        will_renew = auto_renew_status == 1  # 1 = will renew, 0 = won't renew

        logger.info(f"   Auto-renew status: {will_renew}")

        # Update subscription
        update_subscription_renewal_status(
            original_transaction_id=original_transaction_id,
            will_renew=will_renew
        )

        logger.info(f"✅ [Webhook] Renewal status updated")

    except Exception as e:
        logger.error(f"❌ [Webhook] Failed to handle DID_CHANGE_RENEWAL_STATUS: {e}")


def handle_refund(notification_data, transaction_data):
    """Handle refund"""
    logger.info("💸 [Webhook] Handling REFUND event")

    if not transaction_data:
        logger.error("❌ [Webhook] No transaction data for REFUND")
        return

    try:
        original_transaction_id = transaction_data.get('originalTransactionId')
        product_id = transaction_data.get('productId')

        # Revoke access
        update_subscription_status(
            original_transaction_id=original_transaction_id,
            product_id=product_id,
            is_active=False,
            expires_date_ms=None,
            will_renew=False
        )

        logger.info(f"✅ [Webhook] Refund processed, access revoked: {product_id}")

    except Exception as e:
        logger.error(f"❌ [Webhook] Failed to handle REFUND: {e}")


def handle_grace_period_expired(notification_data, transaction_data):
    """Handle grace period expiration"""
    logger.info("⏳ [Webhook] Handling GRACE_PERIOD_EXPIRED event")

    if not transaction_data:
        logger.error("❌ [Webhook] No transaction data for GRACE_PERIOD_EXPIRED")
        return

    try:
        original_transaction_id = transaction_data.get('originalTransactionId')
        product_id = transaction_data.get('productId')

        # Expire subscription
        update_subscription_status(
            original_transaction_id=original_transaction_id,
            product_id=product_id,
            is_active=False,
            expires_date_ms=None,
            will_renew=False
        )

        logger.info(f"✅ [Webhook] Grace period expired, access revoked: {product_id}")

    except Exception as e:
        logger.error(f"❌ [Webhook] Failed to handle GRACE_PERIOD_EXPIRED: {e}")


def update_subscription_status(original_transaction_id, product_id, is_active, expires_date_ms, will_renew, in_billing_retry=False):
    """Update subscription status in database"""
    from flask import current_app

    try:
        firebase_service = current_app.firebase_service

        if not firebase_service.db:
            logger.error("❌ [Webhook] Firebase not configured")
            return

        # Find subscription by original_transaction_id
        subscriptions_ref = firebase_service.db.collection('subscriptions')
        query = subscriptions_ref.where('original_transaction_id', '==', original_transaction_id).limit(1)
        docs = list(query.stream())

        if not docs:
            logger.warning(f"⚠️ [Webhook] No subscription found for transaction: {original_transaction_id}")
            return

        doc = docs[0]

        # Prepare update data
        update_data = {
            'is_active': is_active,
            'product_id': product_id,
            'will_renew': will_renew,
            'in_billing_retry': in_billing_retry,
            'last_updated': datetime.utcnow().isoformat()
        }

        if expires_date_ms:
            # Convert milliseconds to ISO format
            from datetime import datetime
            expires_date = datetime.fromtimestamp(int(expires_date_ms) / 1000)
            update_data['expiration_date'] = expires_date.isoformat()

        # Update document
        doc.reference.update(update_data)

        logger.info(f"✅ [Webhook] Updated subscription in database")
        logger.info(f"   Transaction ID: {original_transaction_id}")
        logger.info(f"   Product: {product_id}")
        logger.info(f"   Active: {is_active}")
        logger.info(f"   Will Renew: {will_renew}")

    except Exception as e:
        logger.error(f"❌ [Webhook] Failed to update subscription: {e}")
        logger.exception(e)


def update_subscription_renewal_status(original_transaction_id, will_renew):
    """Update subscription renewal status"""
    from flask import current_app

    try:
        firebase_service = current_app.firebase_service

        if not firebase_service.db:
            logger.error("❌ [Webhook] Firebase not configured")
            return

        # Find subscription
        subscriptions_ref = firebase_service.db.collection('subscriptions')
        query = subscriptions_ref.where('original_transaction_id', '==', original_transaction_id).limit(1)
        docs = list(query.stream())

        if not docs:
            logger.warning(f"⚠️ [Webhook] No subscription found for transaction: {original_transaction_id}")
            return

        doc = docs[0]

        # Update renewal status
        doc.reference.update({
            'will_renew': will_renew,
            'last_updated': datetime.utcnow().isoformat()
        })

        logger.info(f"✅ [Webhook] Updated renewal status: {will_renew}")

    except Exception as e:
        logger.error(f"❌ [Webhook] Failed to update renewal status: {e}")
