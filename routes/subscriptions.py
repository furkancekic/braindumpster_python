from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import logging
from functools import wraps
import json
import hashlib
import hmac

from services.firebase_service import FirebaseService
from services.regional_pricing_service import RegionalPricingService
from services.purchase_validation_service import PurchaseValidationService, SecurityService
from models.user import User
from models.subscription import Subscription, SubscriptionPlan, SubscriptionStatus
from utils.auth_utils import require_auth
from utils.validation_utils import validate_json_data, ValidationError
from utils.error_handlers import SubscriptionError, PaymentError, handle_api_error
from config import Config

subscriptions_bp = Blueprint('subscriptions', __name__, url_prefix='/subscriptions')

# Initialize services
firebase_service = FirebaseService()
regional_pricing_service = RegionalPricingService()
purchase_validation_service = PurchaseValidationService()
security_service = SecurityService()
logger = logging.getLogger(__name__)

# Subscription validation schemas
PURCHASE_VALIDATION_SCHEMA = {
    'transaction_id': {'type': 'string', 'required': True, 'min': 1, 'max': 500},
    'receipt_data': {'type': 'string', 'required': True, 'min': 1, 'max': 50000},
    'user_id': {'type': 'string', 'required': True, 'min': 1, 'max': 200},
    'platform': {'type': 'string', 'required': True, 'allowed': ['ios', 'android', 'flutter']},
    'product_id': {'type': 'string', 'required': False, 'min': 1, 'max': 200}
}

SUBSCRIPTION_SYNC_SCHEMA = {
    'user_id': {'type': 'string', 'required': True, 'min': 1, 'max': 200},
    'subscription_status': {'type': 'dict', 'required': True},
    'timestamp': {'type': 'string', 'required': True, 'regex': r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'}
}

ENTITLEMENTS_VALIDATION_SCHEMA = {
    'user_id': {'type': 'string', 'required': True, 'min': 1, 'max': 200},
    'entitlements': {'type': 'dict', 'required': True}
}

ANALYTICS_PURCHASE_SCHEMA = {
    'user_id': {'type': 'string', 'required': True, 'min': 1, 'max': 200},
    'product_id': {'type': 'string', 'required': True, 'min': 1, 'max': 200},
    'price': {'type': 'number', 'required': True, 'min': 0, 'max': 10000},
    'currency': {'type': 'string', 'required': True, 'min': 3, 'max': 3},
    'timestamp': {'type': 'string', 'required': True}
}

ANALYTICS_CANCELLATION_SCHEMA = {
    'user_id': {'type': 'string', 'required': True, 'min': 1, 'max': 200},
    'reason': {'type': 'string', 'required': True, 'min': 1, 'max': 500},
    'timestamp': {'type': 'string', 'required': True}
}

@subscriptions_bp.route('/status', methods=['GET'])
def get_subscription_status():
    """Get current subscription status for a user"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'error': 'user_id is required'}), 400

        # Get subscription from Firestore
        subscription = firebase_service.get_user_subscription(user_id)
        
        if not subscription:
            # Return free tier status
            return jsonify({
                'is_active': False,
                'is_premium': False,
                'current_tier': None,
                'expiration_date': None,
                'purchase_date': None,
                'will_renew': False,
                'is_in_grace_period': False
            })

        return jsonify(subscription)  # subscription is already a dict

    except Exception as e:
        logger.error(f"Failed to get subscription status: {e}")
        return jsonify({'error': 'Failed to get subscription status'}), 500


@subscriptions_bp.route('/validate-purchase', methods=['POST'])
@require_auth
def validate_purchase():
    """Validate a purchase with app store and update subscription"""
    try:
        data = validate_json_data(request.get_json(), PURCHASE_VALIDATION_SCHEMA)
        
        transaction_id = data['transaction_id']
        receipt_data = data['receipt_data']
        user_id = data['user_id']
        platform = data['platform']
        product_id = data.get('product_id')

        logger.info(f"Validating purchase for user {user_id}, transaction {transaction_id}")

        # Validate with app store (iOS/Android)
        if platform == 'ios':
            is_valid = _validate_ios_purchase(receipt_data, transaction_id)
        elif platform == 'android':
            is_valid = _validate_android_purchase(receipt_data, transaction_id)
        else:
            # For RevenueCat, we trust the transaction if it comes from authenticated source
            is_valid = True

        if not is_valid:
            logger.warning(f"Purchase validation failed for transaction {transaction_id}")
            return jsonify({'valid': False, 'error': 'Purchase validation failed'}), 400

        # Create or update subscription
        subscription_data = _extract_subscription_data(data, receipt_data, platform)
        
        # Save to Firestore
        firebase_service.save_user_subscription(user_id, subscription_data)
        
        # Log analytics
        _log_purchase_analytics(user_id, product_id, platform, transaction_id)

        logger.info(f"Purchase validated and subscription created for user {user_id}")
        
        return jsonify({
            'valid': True,
            'subscription': subscription_data,
            'message': 'Purchase validated successfully'
        })

    except ValidationError as e:
        logger.error(f"Validation error in validate_purchase: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to validate purchase: {e}")
        return jsonify({'error': 'Failed to validate purchase'}), 500


@subscriptions_bp.route('/sync-status', methods=['POST'])
@require_auth
def sync_subscription_status():
    """Sync subscription status from RevenueCat"""
    try:
        data = validate_json_data(request.get_json(), SUBSCRIPTION_SYNC_SCHEMA)
        
        user_id = data['user_id']
        subscription_status = data['subscription_status']
        
        logger.info(f"Syncing subscription status for user {user_id}")

        # Convert and validate subscription status
        if subscription_status.get('is_premium'):
            subscription_data = _convert_revenuecat_to_subscription_data(subscription_status, user_id)
            firebase_service.save_user_subscription(user_id, subscription_data)
        else:
            # User is on free tier, remove any existing subscription
            firebase_service.delete_user_subscription(user_id)

        return jsonify({
            'success': True,
            'message': 'Subscription status synced successfully'
        })

    except ValidationError as e:
        logger.error(f"Validation error in sync_subscription_status: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to sync subscription status: {e}")
        return jsonify({'error': 'Failed to sync subscription status'}), 500


@subscriptions_bp.route('/validate-entitlements', methods=['POST'])
@require_auth
def validate_entitlements():
    """Validate user entitlements with backend"""
    try:
        data = validate_json_data(request.get_json(), ENTITLEMENTS_VALIDATION_SCHEMA)
        user_id = data['user_id']
        entitlements = data['entitlements']

        # Get current subscription from database
        subscription = firebase_service.get_user_subscription(user_id)
        
        if not subscription:
            # User should only have free entitlements
            if entitlements.get('is_premium'):
                logger.warning(f"User {user_id} claims premium but no subscription found")
                return jsonify({'valid': False, 'message': 'No active subscription found'}), 403

        # Validate entitlements match subscription
        is_valid = _validate_entitlements_match_subscription(entitlements, subscription)
        
        return jsonify({
            'valid': is_valid,
            'message': 'Entitlements validated' if is_valid else 'Entitlements do not match subscription'
        })

    except Exception as e:
        logger.error(f"Failed to validate entitlements: {e}")
        return jsonify({'error': 'Failed to validate entitlements'}), 500


@subscriptions_bp.route('/plans', methods=['GET'])
def get_subscription_plans():
    """Get available subscription plans"""
    try:
        # Get regional pricing if provided
        region = request.args.get('region', 'US')
        
        plans = SubscriptionPlan.get_all_plans()
        
        # Apply regional pricing
        for plan in plans:
            if region in plan.get('regional_pricing', {}):
                plan['price'] = plan['regional_pricing'][region]
        
        return jsonify({'plans': plans})

    except Exception as e:
        logger.error(f"Failed to get subscription plans: {e}")
        return jsonify({'error': 'Failed to get subscription plans'}), 500


@subscriptions_bp.route('/regional-pricing', methods=['GET'])
def get_regional_pricing():
    """Get regional pricing for a product"""
    try:
        product_id = request.args.get('product_id')
        country_code = request.args.get('country_code')
        
        if not product_id:
            return jsonify({'error': 'product_id is required'}), 400
        
        if country_code:
            # Get pricing for specific country
            base_prices = {
                'brain_dumpster_monthly_premium': 9.99,
                'brain_dumpster_yearly_premium': 79.99,
                'brain_dumpster_lifetime_premium': 199.99,
                'monthly_premium': 9.99,
                'yearly_premium': 79.99,
                'lifetime_premium': 199.99,
            }
            
            base_price_usd = base_prices.get(product_id)
            if not base_price_usd:
                return jsonify({'error': 'Unknown product_id'}), 400
                
            pricing = regional_pricing_service.get_regional_pricing(base_price_usd, country_code)
            return jsonify({'pricing': pricing})
        else:
            # Get pricing for all regions
            pricing = _get_regional_pricing_for_product(product_id)
            return jsonify({'pricing': pricing})

    except Exception as e:
        logger.error(f"Failed to get regional pricing: {e}")
        return jsonify({'error': 'Failed to get regional pricing'}), 500


@subscriptions_bp.route('/supported-countries', methods=['GET'])
def get_supported_countries():
    """Get list of supported countries for regional pricing"""
    try:
        countries = regional_pricing_service.get_supported_countries()
        
        # Add additional metadata
        countries_info = []
        for country_code in countries:
            strategy_info = regional_pricing_service.get_pricing_strategy_info(country_code)
            countries_info.append(strategy_info)
        
        return jsonify({
            'supported_countries': countries,
            'countries_info': countries_info
        })
    
    except Exception as e:
        logger.error(f"Failed to get supported countries: {e}")
        return jsonify({'error': 'Failed to get supported countries'}), 500


@subscriptions_bp.route('/detect-region', methods=['POST'])
def detect_user_region():
    """Detect user's region based on IP address"""
    try:
        data = request.get_json() or {}
        ip_address = data.get('ip_address') or request.remote_addr
        user_agent = data.get('user_agent') or request.headers.get('User-Agent')
        
        region = regional_pricing_service.detect_user_region(ip_address, user_agent)
        strategy_info = regional_pricing_service.get_pricing_strategy_info(region)
        
        return jsonify({
            'detected_region': region,
            'region_info': strategy_info
        })
    
    except Exception as e:
        logger.error(f"Failed to detect region: {e}")
        return jsonify({
            'detected_region': 'US',  # Default fallback
            'region_info': regional_pricing_service.get_pricing_strategy_info('US')
        })


@subscriptions_bp.route('/pricing-comparison', methods=['GET'])
def get_pricing_comparison():
    """Compare prices across multiple countries"""
    try:
        product_id = request.args.get('product_id')
        countries = request.args.get('countries', '').split(',') if request.args.get('countries') else ['US', 'GB', 'IN', 'BR', 'DE', 'JP']
        
        if not product_id:
            return jsonify({'error': 'product_id is required'}), 400
        
        # Remove empty strings and validate countries
        countries = [c.strip().upper() for c in countries if c.strip()]
        countries = [c for c in countries if regional_pricing_service.validate_country_code(c)]
        
        if not countries:
            return jsonify({'error': 'No valid country codes provided'}), 400
        
        base_prices = {
            'brain_dumpster_monthly_premium': 9.99,
            'brain_dumpster_yearly_premium': 79.99,
            'brain_dumpster_lifetime_premium': 199.99,
            'monthly_premium': 9.99,
            'yearly_premium': 79.99,
            'lifetime_premium': 199.99,
        }
        
        base_price_usd = base_prices.get(product_id)
        if not base_price_usd:
            return jsonify({'error': 'Unknown product_id'}), 400
        
        comparison = regional_pricing_service.get_price_comparison(base_price_usd, countries)
        
        return jsonify(comparison)
    
    except Exception as e:
        logger.error(f"Failed to get pricing comparison: {e}")
        return jsonify({'error': 'Failed to get pricing comparison'}), 500


@subscriptions_bp.route('/analytics/purchase', methods=['POST'])
@require_auth
def log_purchase_analytics():
    """Log purchase analytics event"""
    try:
        data = validate_json_data(request.get_json(), ANALYTICS_PURCHASE_SCHEMA)
        
        user_id = data['user_id']
        product_id = data['product_id']
        price = data['price']
        currency = data['currency']
        timestamp = data['timestamp']

        # Log to analytics service
        analytics_data = {
            'user_id': user_id,
            'event': 'subscription_purchase',
            'product_id': product_id,
            'price': price,
            'currency': currency,
            'timestamp': timestamp or datetime.utcnow().isoformat(),
            'platform': 'flutter'
        }
        
        firebase_service.log_analytics_event('subscription_purchase', analytics_data)
        
        return jsonify({'success': True, 'message': 'Analytics logged successfully'})

    except Exception as e:
        logger.error(f"Failed to log purchase analytics: {e}")
        return jsonify({'error': 'Failed to log analytics'}), 500


@subscriptions_bp.route('/analytics/cancellation', methods=['POST'])
@require_auth
def log_cancellation_analytics():
    """Log subscription cancellation analytics event"""
    try:
        data = validate_json_data(request.get_json(), ANALYTICS_CANCELLATION_SCHEMA)
        
        user_id = data['user_id']
        reason = data['reason']
        timestamp = data['timestamp']

        # Log to analytics service
        analytics_data = {
            'user_id': user_id,
            'event': 'subscription_cancellation',
            'reason': reason,
            'timestamp': timestamp,
            'platform': 'flutter'
        }
        
        firebase_service.log_analytics_event('subscription_cancellation', analytics_data)
        
        return jsonify({'success': True, 'message': 'Cancellation logged successfully'})

    except Exception as e:
        logger.error(f"Failed to log cancellation analytics: {e}")
        return jsonify({'error': 'Failed to log analytics'}), 500


@subscriptions_bp.route('/webhook/revenuecat', methods=['POST'])
def revenuecat_webhook():
    """Handle RevenueCat webhooks for subscription events"""
    try:
        # Verify webhook signature
        if not _verify_revenuecat_webhook(request):
            logger.warning("RevenueCat webhook signature verification failed")
            return jsonify({'error': 'Invalid signature'}), 401

        data = request.get_json()
        event_type = data.get('event_type')
        
        logger.info(f"Received RevenueCat webhook: {event_type}")

        if event_type in ['initial_purchase', 'renewal', 'product_change']:
            _handle_subscription_activation(data)
        elif event_type in ['cancellation', 'expiration']:
            _handle_subscription_deactivation(data)
        elif event_type == 'billing_issue':
            _handle_billing_issue(data)

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Failed to process RevenueCat webhook: {e}")
        return jsonify({'error': 'Webhook processing failed'}), 500


# Private helper functions

def _validate_ios_purchase(receipt_data, transaction_id):
    """Validate iOS purchase with App Store"""
    logger.info(f"iOS purchase validation for transaction {transaction_id}")
    
    try:
        is_valid, validation_data = purchase_validation_service.validate_ios_purchase(receipt_data, transaction_id)
        
        if is_valid:
            logger.info(f"iOS purchase validated successfully: {transaction_id}")
            return True
        else:
            logger.warning(f"iOS purchase validation failed: {validation_data.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"iOS purchase validation error: {e}")
        return False


def _validate_android_purchase(receipt_data, transaction_id):
    """Validate Android purchase with Google Play"""
    logger.info(f"Android purchase validation for transaction {transaction_id}")
    
    try:
        is_valid, validation_data = purchase_validation_service.validate_android_purchase(receipt_data, transaction_id)
        
        if is_valid:
            logger.info(f"Android purchase validated successfully: {transaction_id}")
            return True
        else:
            logger.warning(f"Android purchase validation failed: {validation_data.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"Android purchase validation error: {e}")
        return False


def _extract_subscription_data(purchase_data, receipt_data, platform):
    """Extract subscription data from purchase information"""
    product_id = purchase_data.get('product_id', '')
    
    # Determine subscription tier and duration from product_id
    if 'monthly' in product_id.lower():
        tier = 'monthly_premium'
        duration_months = 1
    elif 'yearly' in product_id.lower():
        tier = 'yearly_premium'
        duration_months = 12
    elif 'lifetime' in product_id.lower():
        tier = 'lifetime_premium'
        duration_months = None
    else:
        tier = 'monthly_premium'  # Default
        duration_months = 1

    now = datetime.utcnow()
    expiration_date = now + timedelta(days=duration_months * 30) if duration_months else None

    return {
        'user_id': purchase_data['user_id'],
        'tier': tier,
        'status': 'active',
        'purchase_date': now.isoformat(),
        'expiration_date': expiration_date.isoformat() if expiration_date else None,
        'transaction_id': purchase_data['transaction_id'],
        'platform': platform,
        'is_active': True,
        'will_renew': duration_months is not None,
        'created_at': now.isoformat(),
        'updated_at': now.isoformat()
    }


def _convert_revenuecat_to_subscription_data(revenuecat_data, user_id):
    """Convert RevenueCat data to subscription data"""
    current_tier = revenuecat_data.get('current_tier', {})
    
    # Map RevenueCat tier to our tier system
    tier = 'monthly_premium'
    if current_tier:
        if 'yearly' in current_tier.get('id', '').lower():
            tier = 'yearly_premium'
        elif 'lifetime' in current_tier.get('id', '').lower():
            tier = 'lifetime_premium'
    
    expiration_date = None
    if revenuecat_data.get('expiration_date'):
        try:
            expiration_date = datetime.fromisoformat(
                revenuecat_data['expiration_date'].replace('Z', '+00:00')
            ).isoformat()
        except:
            pass

    purchase_date = None
    if revenuecat_data.get('purchase_date'):
        try:
            purchase_date = datetime.fromisoformat(
                revenuecat_data['purchase_date'].replace('Z', '+00:00')
            ).isoformat()
        except:
            pass

    return {
        'user_id': user_id,
        'tier': tier,
        'status': 'active' if revenuecat_data.get('is_active') else 'expired',
        'purchase_date': purchase_date,
        'expiration_date': expiration_date,
        'transaction_id': revenuecat_data.get('transaction_id'),
        'platform': 'revenuecat',
        'is_active': revenuecat_data.get('is_active', False),
        'will_renew': revenuecat_data.get('will_renew', True),
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }


def _validate_entitlements_match_subscription(entitlements, subscription):
    """Validate that entitlements match the user's subscription"""
    if not subscription:
        return not entitlements.get('is_premium', False)
    
    # Check if subscription is still active
    if subscription.get('expiration_date'):
        expiration = datetime.fromisoformat(subscription['expiration_date'].replace('Z', '+00:00'))
        if expiration < datetime.utcnow():
            return not entitlements.get('is_premium', False)
    
    # If subscription is active, user should have premium entitlements
    return entitlements.get('is_premium', False)


def _get_regional_pricing_for_product(product_id):
    """Get regional pricing for a product using the regional pricing service"""
    try:
        # Map product_id to base USD price
        base_prices = {
            'brain_dumpster_monthly_premium': 9.99,
            'brain_dumpster_yearly_premium': 79.99,
            'brain_dumpster_lifetime_premium': 199.99,
            'monthly_premium': 9.99,  # RevenueCat identifiers
            'yearly_premium': 79.99,
            'lifetime_premium': 199.99,
        }
        
        base_price_usd = base_prices.get(product_id)
        if not base_price_usd:
            logger.warning(f"Unknown product_id for pricing: {product_id}")
            return {}
        
        # Get pricing for all regions
        regional_pricing = regional_pricing_service.get_all_regional_pricing(base_price_usd)
        
        # Convert to simple country_code -> price mapping
        pricing_map = {}
        for country_code, pricing_info in regional_pricing.items():
            pricing_map[country_code] = pricing_info['price']
        
        return pricing_map
        
    except Exception as e:
        logger.error(f"Failed to get regional pricing for {product_id}: {e}")
        # Fallback to basic pricing
        return {'US': 9.99 if 'monthly' in product_id else 79.99 if 'yearly' in product_id else 199.99}


def _log_purchase_analytics(user_id, product_id, platform, transaction_id):
    """Log purchase analytics"""
    analytics_data = {
        'user_id': user_id,
        'product_id': product_id,
        'platform': platform,
        'transaction_id': transaction_id,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    firebase_service.log_analytics_event('subscription_purchase', analytics_data)


def _verify_revenuecat_webhook(request):
    """Verify RevenueCat webhook signature"""
    try:
        signature = request.headers.get('X-RevenueCat-Signature')
        if not signature:
            logger.warning("Missing RevenueCat signature header")
            return False
        
        payload = request.get_data()
        
        is_valid = purchase_validation_service.verify_revenuecat_webhook(payload, signature)
        
        if is_valid:
            logger.info("RevenueCat webhook signature verified")
        else:
            logger.warning("RevenueCat webhook signature verification failed")
        
        return is_valid
        
    except Exception as e:
        logger.error(f"RevenueCat webhook verification error: {e}")
        return False


def _handle_subscription_activation(webhook_data):
    """Handle subscription activation webhook"""
    app_user_id = webhook_data.get('app_user_id')
    if not app_user_id:
        return

    # Update subscription status in database
    subscription_data = {
        'user_id': app_user_id,
        'status': 'active',
        'tier': 'premium',
        'is_active': True,
        'updated_at': datetime.utcnow().isoformat()
    }
    
    firebase_service.save_user_subscription(app_user_id, subscription_data)


def _handle_subscription_deactivation(webhook_data):
    """Handle subscription deactivation webhook"""
    app_user_id = webhook_data.get('app_user_id')
    if not app_user_id:
        return

    # Update subscription status in database
    firebase_service.deactivate_user_subscription(app_user_id)


def _handle_billing_issue(webhook_data):
    """Handle billing issue webhook"""
    app_user_id = webhook_data.get('app_user_id')
    if not app_user_id:
        return

    # Send notification to user about billing issue
    # TODO(context7): Implement billing issue notification
    logger.warning(f"Billing issue for user {app_user_id}")