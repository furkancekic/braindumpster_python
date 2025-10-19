import requests
import json
import base64
import hashlib
import hmac
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple
from config import Config

logger = logging.getLogger(__name__)

class PurchaseValidationService:
    """Service for validating in-app purchases with App Store and Google Play"""
    
    # Apple App Store URLs
    APPLE_SANDBOX_URL = "https://sandbox.itunes.apple.com/verifyReceipt"
    APPLE_PRODUCTION_URL = "https://buy.itunes.apple.com/verifyReceipt"
    
    # Google Play API base URL
    GOOGLE_PLAY_BASE_URL = "https://androidpublisher.googleapis.com/androidpublisher/v3"
    
    def __init__(self):
        self.apple_shared_secret = Config.APPLE_SHARED_SECRET if hasattr(Config, 'APPLE_SHARED_SECRET') else None
        self.google_service_account_key = Config.GOOGLE_SERVICE_ACCOUNT_KEY if hasattr(Config, 'GOOGLE_SERVICE_ACCOUNT_KEY') else None
        self.revenuecat_webhook_secret = Config.REVENUECAT_WEBHOOK_SECRET if hasattr(Config, 'REVENUECAT_WEBHOOK_SECRET') else None
    
    def validate_ios_receipt(self, receipt_data: str) -> Tuple[bool, Dict]:
        """
        Validate iOS App Store receipt (StoreKit 2 compatible)

        Implements Apple's recommended approach:
        1. Always validate against production first
        2. If status code 21007 (sandbox receipt in production), retry with sandbox
        3. If status code 21008 (production receipt in sandbox), retry with production

        Args:
            receipt_data: Base64-encoded receipt data

        Returns:
            Tuple[bool, Dict]: (is_valid, validation_data)
        """
        try:
            logger.info("🍎 [Apple Receipt Validation] Starting validation process")
            logger.info("   Step 1: Validating against PRODUCTION endpoint first (Apple's recommendation)")

            # Prepare receipt data
            receipt_payload = {
                "receipt-data": receipt_data,
                "password": self.apple_shared_secret,
                "exclude-old-transactions": False  # Get all transactions for latest purchase
            }

            # STEP 1: Always try production first (Apple's recommended approach)
            validation_result = self._validate_with_apple(receipt_payload, production=True)
            logger.info(f"   Production validation result: status={validation_result.get('status')}")

            # STEP 2: Handle environment mismatch
            if validation_result['status'] == 21007:  # Sandbox receipt sent to production
                logger.info("   ⚠️  Status 21007: Sandbox receipt detected in production request")
                logger.info("   Step 2: Retrying with SANDBOX endpoint")
                validation_result = self._validate_with_apple(receipt_payload, production=False)
                logger.info(f"   Sandbox validation result: status={validation_result.get('status')}")
            elif validation_result['status'] == 21008:  # Production receipt sent to sandbox (shouldn't happen but handle it)
                logger.info("   ⚠️  Status 21008: Production receipt detected (unexpected)")
                logger.info("   Step 2: Retrying with PRODUCTION endpoint")
                validation_result = self._validate_with_apple(receipt_payload, production=True)
                logger.info(f"   Production retry result: status={validation_result.get('status')}")

            if validation_result['status'] == 0:  # Success
                # Extract relevant purchase information
                receipt_info = validation_result.get('receipt', {})
                in_app_purchases = receipt_info.get('in_app', [])

                # Get the most recent purchase
                if in_app_purchases:
                    # Sort by purchase date (most recent first)
                    sorted_purchases = sorted(
                        in_app_purchases,
                        key=lambda x: int(x.get('purchase_date_ms', 0)),
                        reverse=True
                    )
                    latest_purchase = sorted_purchases[0]

                    # Convert expiration date to ISO format if present
                    expiration_date = None
                    if latest_purchase.get('expires_date_ms'):
                        try:
                            from datetime import datetime
                            exp_timestamp = int(latest_purchase['expires_date_ms']) / 1000
                            expiration_date = datetime.fromtimestamp(exp_timestamp).isoformat()
                        except:
                            pass

                    # Determine environment
                    environment = 'sandbox' if validation_result.get('environment') == 'Sandbox' else 'production'

                    validation_data = {
                        'transaction_id': latest_purchase.get('transaction_id'),
                        'product_id': latest_purchase.get('product_id'),
                        'purchase_date': latest_purchase.get('purchase_date_ms'),
                        'expiration_date': expiration_date,
                        'is_trial_period': latest_purchase.get('is_trial_period', 'false') == 'true',
                        'is_in_intro_offer_period': latest_purchase.get('is_in_intro_offer_period', 'false') == 'true',
                        'bundle_id': receipt_info.get('bundle_id'),
                        'application_version': receipt_info.get('application_version'),
                        'environment': environment
                    }

                    logger.info(f"iOS receipt validated successfully: {latest_purchase.get('product_id')}")
                    return True, validation_data
                else:
                    logger.warning("No in-app purchases found in receipt")
                    return False, {'error': 'No purchases found in receipt'}
            else:
                error_msg = self._get_apple_status_message(validation_result['status'])
                logger.warning(f"Apple receipt validation failed: status={validation_result['status']} - {error_msg}")
                return False, {'error': error_msg}

        except Exception as e:
            logger.error(f"iOS receipt validation error: {e}")
            return False, {'error': str(e)}

    def validate_ios_purchase(self, receipt_data: str, transaction_id: str) -> Tuple[bool, Dict]:
        """
        Validate iOS in-app purchase receipt with Apple App Store

        Implements Apple's recommended approach:
        1. Always validate against production first
        2. If status code 21007 (sandbox receipt in production), retry with sandbox
        3. If status code 21008 (production receipt in sandbox), retry with production

        Returns:
            Tuple[bool, Dict]: (is_valid, validation_data)
        """
        try:
            logger.info(f"🍎 [Apple Receipt Validation] Validating purchase: transaction_id={transaction_id}")
            logger.info("   Step 1: Validating against PRODUCTION endpoint first")

            # Prepare receipt data
            receipt_payload = {
                "receipt-data": receipt_data,
                "password": self.apple_shared_secret,
                "exclude-old-transactions": True
            }

            # STEP 1: Always try production first (Apple's recommended approach)
            validation_result = self._validate_with_apple(receipt_payload, production=True)
            logger.info(f"   Production validation result: status={validation_result.get('status')}")

            # STEP 2: Handle environment mismatch
            if validation_result['status'] == 21007:  # Sandbox receipt sent to production
                logger.info("   ⚠️  Status 21007: Sandbox receipt detected in production request")
                logger.info("   Step 2: Retrying with SANDBOX endpoint")
                validation_result = self._validate_with_apple(receipt_payload, production=False)
                logger.info(f"   Sandbox validation result: status={validation_result.get('status')}")
            elif validation_result['status'] == 21008:  # Production receipt sent to sandbox
                logger.info("   ⚠️  Status 21008: Production receipt detected (unexpected)")
                logger.info("   Step 2: Retrying with PRODUCTION endpoint")
                validation_result = self._validate_with_apple(receipt_payload, production=True)
                logger.info(f"   Production retry result: status={validation_result.get('status')}")

            if validation_result['status'] == 0:  # Success
                # Extract relevant purchase information
                receipt_info = validation_result.get('receipt', {})
                in_app_purchases = receipt_info.get('in_app', [])

                # Find the specific transaction
                target_transaction = None
                for purchase in in_app_purchases:
                    if purchase.get('transaction_id') == transaction_id:
                        target_transaction = purchase
                        break

                if target_transaction:
                    validation_data = {
                        'transaction_id': target_transaction.get('transaction_id'),
                        'product_id': target_transaction.get('product_id'),
                        'purchase_date': target_transaction.get('purchase_date_ms'),
                        'expires_date': target_transaction.get('expires_date_ms'),
                        'is_trial_period': target_transaction.get('is_trial_period', 'false') == 'true',
                        'is_in_intro_offer_period': target_transaction.get('is_in_intro_offer_period', 'false') == 'true',
                        'bundle_id': receipt_info.get('bundle_id'),
                        'application_version': receipt_info.get('application_version')
                    }

                    logger.info(f"iOS purchase validated successfully: {target_transaction.get('product_id')}")
                    return True, validation_data
                else:
                    logger.warning(f"Transaction {transaction_id} not found in receipt")
                    return False, {'error': 'Transaction not found in receipt'}
            else:
                logger.warning(f"Apple receipt validation failed: status={validation_result['status']}")
                return False, {'error': f"Apple validation failed: {validation_result.get('status')}"}

        except Exception as e:
            logger.error(f"iOS purchase validation error: {e}")
            return False, {'error': str(e)}
    
    def validate_android_purchase(self, receipt_data: str, transaction_id: str) -> Tuple[bool, Dict]:
        """
        Validate Android in-app purchase with Google Play
        
        Returns:
            Tuple[bool, Dict]: (is_valid, validation_data)
        """
        try:
            logger.info(f"Validating Android purchase: transaction_id={transaction_id}")
            
            # Parse receipt data (should contain purchase token and product ID)
            try:
                receipt_json = json.loads(receipt_data)
                purchase_token = receipt_json.get('purchaseToken')
                product_id = receipt_json.get('productId')
                package_name = receipt_json.get('packageName')
            except json.JSONDecodeError:
                logger.error("Invalid receipt data format for Android")
                return False, {'error': 'Invalid receipt data format'}
            
            if not all([purchase_token, product_id, package_name]):
                logger.error("Missing required fields in Android receipt")
                return False, {'error': 'Missing required fields in receipt'}
            
            # Get access token for Google Play API
            access_token = self._get_google_play_access_token()
            if not access_token:
                logger.error("Failed to get Google Play access token")
                return False, {'error': 'Failed to authenticate with Google Play'}
            
            # Validate purchase with Google Play API
            url = f"{self.GOOGLE_PLAY_BASE_URL}/applications/{package_name}/purchases/products/{product_id}/tokens/{purchase_token}"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                purchase_data = response.json()
                
                # Check if purchase is valid
                purchase_state = purchase_data.get('purchaseState')
                if purchase_state == 0:  # Purchased
                    validation_data = {
                        'transaction_id': transaction_id,
                        'product_id': product_id,
                        'purchase_time': purchase_data.get('purchaseTimeMillis'),
                        'purchase_state': purchase_state,
                        'consumption_state': purchase_data.get('consumptionState'),
                        'developer_payload': purchase_data.get('developerPayload'),
                        'order_id': purchase_data.get('orderId'),
                        'package_name': package_name
                    }
                    
                    logger.info(f"Android purchase validated successfully: {product_id}")
                    return True, validation_data
                else:
                    logger.warning(f"Android purchase not in valid state: {purchase_state}")
                    return False, {'error': f'Purchase state invalid: {purchase_state}'}
            else:
                logger.error(f"Google Play API validation failed: {response.status_code}")
                return False, {'error': f'Google Play validation failed: {response.status_code}'}
                
        except Exception as e:
            logger.error(f"Android purchase validation error: {e}")
            return False, {'error': str(e)}
    
    def verify_revenuecat_webhook(self, payload: bytes, signature: str) -> bool:
        """
        Verify RevenueCat webhook signature
        
        Args:
            payload: Raw webhook payload
            signature: Signature from X-RevenueCat-Signature header
            
        Returns:
            bool: True if signature is valid
        """
        try:
            if not self.revenuecat_webhook_secret:
                logger.warning("RevenueCat webhook secret not configured")
                return True  # Allow in development
            
            # RevenueCat uses HMAC-SHA256
            expected_signature = hmac.new(
                self.revenuecat_webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures securely
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            logger.error(f"RevenueCat webhook verification error: {e}")
            return False
    
    def validate_purchase_receipt(self, platform: str, receipt_data: str, transaction_id: str) -> Tuple[bool, Dict]:
        """
        Validate purchase receipt based on platform
        
        Args:
            platform: 'ios', 'android', or 'revenuecat'
            receipt_data: Receipt data from the platform
            transaction_id: Transaction identifier
            
        Returns:
            Tuple[bool, Dict]: (is_valid, validation_data)
        """
        platform = platform.lower()
        
        if platform == 'ios':
            return self.validate_ios_purchase(receipt_data, transaction_id)
        elif platform == 'android':
            return self.validate_android_purchase(receipt_data, transaction_id)
        elif platform in ['revenuecat', 'flutter']:
            # For RevenueCat, we trust the webhook validation
            logger.info(f"Trusting RevenueCat validation for transaction: {transaction_id}")
            return True, {
                'transaction_id': transaction_id,
                'platform': platform,
                'validated_by': 'revenuecat',
                'validation_time': datetime.utcnow().isoformat()
            }
        else:
            logger.error(f"Unsupported platform for purchase validation: {platform}")
            return False, {'error': f'Unsupported platform: {platform}'}
    
    def _validate_with_apple(self, receipt_payload: Dict, production: bool = True) -> Dict:
        """
        Make request to Apple's receipt validation servers

        Args:
            receipt_payload: Receipt data with password and options
            production: If True, use production endpoint; if False, use sandbox endpoint

        Returns:
            Dict: Apple's validation response with status code
        """
        url = self.APPLE_PRODUCTION_URL if production else self.APPLE_SANDBOX_URL
        env_name = "PRODUCTION" if production else "SANDBOX"

        logger.info(f"   📤 Sending validation request to Apple {env_name} endpoint")
        logger.info(f"   URL: {url}")

        try:
            response = requests.post(
                url,
                json=receipt_payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                status = result.get('status')
                logger.info(f"   📥 Apple response received: status={status}")

                if status == 0:
                    logger.info(f"   ✅ Receipt validation SUCCESSFUL on {env_name}")
                else:
                    status_msg = self._get_apple_status_message(status)
                    logger.warning(f"   ⚠️  Receipt validation failed: {status_msg}")

                return result
            else:
                logger.error(f"   ❌ Apple API HTTP error: {response.status_code}")
                logger.error(f"   Response: {response.text[:200]}")
                return {'status': -1, 'error': 'Network error'}

        except requests.exceptions.Timeout:
            logger.error(f"   ❌ Apple API request timeout (30s)")
            return {'status': -1, 'error': 'Request timeout'}
        except Exception as e:
            logger.error(f"   ❌ Apple API request exception: {e}")
            return {'status': -1, 'error': str(e)}
    
    def _get_google_play_access_token(self) -> Optional[str]:
        """Get access token for Google Play API using service account"""
        try:
            # TODO(context7): Implement Google service account authentication
            # This requires the Google Auth library and service account JSON
            # For now, return None to indicate authentication not configured

            if not self.google_service_account_key:
                logger.warning("Google service account key not configured")
                return None

            # from google.auth.transport.requests import Request
            # from google.oauth2 import service_account
            #
            # credentials = service_account.Credentials.from_service_account_info(
            #     self.google_service_account_key,
            #     scopes=['https://www.googleapis.com/auth/androidpublisher']
            # )
            # credentials.refresh(Request())
            # return credentials.token

            logger.warning("Google Play validation not fully implemented")
            return None

        except Exception as e:
            logger.error(f"Failed to get Google Play access token: {e}")
            return None

    def _get_apple_status_message(self, status_code: int) -> str:
        """Get human-readable message for Apple receipt validation status codes"""
        status_messages = {
            0: "Valid receipt",
            21000: "The App Store could not read the JSON object you provided",
            21002: "The data in the receipt-data property was malformed or missing",
            21003: "The receipt could not be authenticated",
            21004: "The shared secret you provided does not match the shared secret on file",
            21005: "The receipt server is not currently available",
            21006: "This receipt is valid but the subscription has expired",
            21007: "This receipt is from the test environment (sandbox)",
            21008: "This receipt is from the production environment",
            21009: "Internal data access error",
            21010: "The user account cannot be found or has been deleted"
        }
        return status_messages.get(status_code, f"Unknown status code: {status_code}")
    
    def get_validation_summary(self, validations: list) -> Dict:
        """Get summary of validation results"""
        total = len(validations)
        successful = sum(1 for v in validations if v.get('is_valid'))
        failed = total - successful
        
        platforms = {}
        for validation in validations:
            platform = validation.get('platform', 'unknown')
            platforms[platform] = platforms.get(platform, 0) + 1
        
        return {
            'total_validations': total,
            'successful': successful,
            'failed': failed,
            'success_rate': (successful / total * 100) if total > 0 else 0,
            'platforms': platforms,
            'last_validation': max(validations, key=lambda x: x.get('timestamp', '')) if validations else None
        }

class SecurityService:
    """Additional security utilities for subscription system"""
    
    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate a cryptographically secure random token"""
        import secrets
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def hash_sensitive_data(data: str) -> str:
        """Hash sensitive data using SHA-256"""
        return hashlib.sha256(data.encode('utf-8')).hexdigest()
    
    @staticmethod
    def validate_timestamp(timestamp_str: str, max_age_seconds: int = 300) -> bool:
        """Validate that timestamp is recent (within max_age_seconds)"""
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            age = (datetime.utcnow() - timestamp).total_seconds()
            return age <= max_age_seconds
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def sanitize_user_data(data: Dict) -> Dict:
        """Sanitize user data by removing sensitive fields"""
        sensitive_fields = ['password', 'token', 'secret', 'key', 'receipt_data']
        
        if not isinstance(data, dict):
            return data
        
        sanitized = {}
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in sensitive_fields):
                sanitized[key] = '[REDACTED]'
            elif isinstance(value, dict):
                sanitized[key] = SecurityService.sanitize_user_data(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    @staticmethod
    def rate_limit_key(user_id: str, endpoint: str) -> str:
        """Generate rate limit key for Redis/caching"""
        return f"rate_limit:{user_id}:{endpoint}"
    
    @staticmethod
    def is_suspicious_activity(user_id: str, actions: list) -> bool:
        """Detect suspicious activity patterns"""
        # Simple heuristics for suspicious activity
        if len(actions) > 10:  # Too many actions in short time
            return True
        
        # Check for rapid subscription changes
        subscription_actions = [a for a in actions if 'subscription' in a.get('action', '').lower()]
        if len(subscription_actions) > 3:
            return True
        
        return False