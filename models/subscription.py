from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional
import json

class SubscriptionStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"
    GRACE_PERIOD = "grace_period"
    BILLING_ISSUE = "billing_issue"

class SubscriptionTier(Enum):
    FREE = "free"
    MONTHLY_PREMIUM = "monthly_premium"
    YEARLY_PREMIUM = "yearly_premium"
    LIFETIME_PREMIUM = "lifetime_premium"

class Subscription:
    def __init__(
        self,
        user_id: str,
        tier: str,
        status: str,
        purchase_date: datetime = None,
        expiration_date: datetime = None,
        transaction_id: str = None,
        platform: str = None,
        will_renew: bool = True,
        is_active: bool = True,
        created_at: datetime = None,
        updated_at: datetime = None
    ):
        self.user_id = user_id
        self.tier = tier
        self.status = status
        self.purchase_date = purchase_date or datetime.utcnow()
        self.expiration_date = expiration_date
        self.transaction_id = transaction_id
        self.platform = platform
        self.will_renew = will_renew
        self.is_active = is_active
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()

    def to_dict(self) -> Dict:
        """Convert subscription to dictionary"""
        return {
            "user_id": self.user_id,
            "tier": self.tier,
            "status": self.status,
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
            "transaction_id": self.transaction_id,
            "platform": self.platform,
            "will_renew": self.will_renew,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            
            # Additional fields for Flutter app compatibility
            "is_premium": self.is_premium(),
            "current_tier": self.get_tier_info(),
        }

    @classmethod
    def from_dict(cls, data: Dict):
        """Create subscription from dictionary"""
        return cls(
            user_id=data["user_id"],
            tier=data["tier"],
            status=data["status"],
            purchase_date=datetime.fromisoformat(data["purchase_date"]) if data.get("purchase_date") else None,
            expiration_date=datetime.fromisoformat(data["expiration_date"]) if data.get("expiration_date") else None,
            transaction_id=data.get("transaction_id"),
            platform=data.get("platform"),
            will_renew=data.get("will_renew", True),
            is_active=data.get("is_active", True),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
        )

    @classmethod
    def from_revenuecat_data(cls, revenuecat_data: Dict, user_id: str):
        """Create subscription from RevenueCat webhook/API data"""
        current_tier = revenuecat_data.get("current_tier")
        expiration_date = None
        
        if revenuecat_data.get("expiration_date"):
            try:
                expiration_date = datetime.fromisoformat(
                    revenuecat_data["expiration_date"].replace('Z', '+00:00')
                )
            except:
                pass

        purchase_date = None
        if revenuecat_data.get("purchase_date"):
            try:
                purchase_date = datetime.fromisoformat(
                    revenuecat_data["purchase_date"].replace('Z', '+00:00')
                )
            except:
                pass

        # Map RevenueCat tier to our tier system
        tier = SubscriptionTier.MONTHLY_PREMIUM.value
        if current_tier:
            if "yearly" in current_tier.get("id", "").lower():
                tier = SubscriptionTier.YEARLY_PREMIUM.value
            elif "lifetime" in current_tier.get("id", "").lower():
                tier = SubscriptionTier.LIFETIME_PREMIUM.value

        return cls(
            user_id=user_id,
            tier=tier,
            status=SubscriptionStatus.ACTIVE.value if revenuecat_data.get("is_active") else SubscriptionStatus.EXPIRED.value,
            purchase_date=purchase_date,
            expiration_date=expiration_date,
            transaction_id=revenuecat_data.get("transaction_id"),
            platform="revenuecat",
            will_renew=revenuecat_data.get("will_renew", True),
            is_active=revenuecat_data.get("is_active", False)
        )

    def is_premium(self) -> bool:
        """Check if subscription provides premium access"""
        if self.tier == SubscriptionTier.FREE.value:
            return False
            
        if not self.is_active:
            return False
            
        # Check if subscription has expired
        if self.expiration_date and self.expiration_date < datetime.utcnow():
            return False
            
        return self.status in [SubscriptionStatus.ACTIVE.value, SubscriptionStatus.GRACE_PERIOD.value]

    def get_tier_info(self) -> Optional[Dict]:
        """Get detailed tier information"""
        tier_info = SubscriptionPlan.get_plan_by_id(self.tier)
        return tier_info

    def is_expired(self) -> bool:
        """Check if subscription has expired"""
        if not self.expiration_date:
            return False  # Lifetime subscriptions never expire
        return self.expiration_date < datetime.utcnow()

    def days_until_expiration(self) -> Optional[int]:
        """Get number of days until expiration"""
        if not self.expiration_date:
            return None  # Lifetime subscription
        
        delta = self.expiration_date - datetime.utcnow()
        return max(0, delta.days)

    def renew(self, duration_months: int = None) -> None:
        """Renew subscription"""
        if self.tier == SubscriptionTier.LIFETIME_PREMIUM.value:
            return  # Lifetime subscriptions don't need renewal
        
        if duration_months is None:
            if self.tier == SubscriptionTier.MONTHLY_PREMIUM.value:
                duration_months = 1
            elif self.tier == SubscriptionTier.YEARLY_PREMIUM.value:
                duration_months = 12
            else:
                duration_months = 1

        # Extend expiration date
        if self.expiration_date and self.expiration_date > datetime.utcnow():
            # Extend from current expiration
            self.expiration_date += timedelta(days=duration_months * 30)
        else:
            # Extend from now
            self.expiration_date = datetime.utcnow() + timedelta(days=duration_months * 30)
        
        self.status = SubscriptionStatus.ACTIVE.value
        self.is_active = True
        self.updated_at = datetime.utcnow()

    def cancel(self) -> None:
        """Cancel subscription"""
        self.status = SubscriptionStatus.CANCELLED.value
        self.will_renew = False
        self.updated_at = datetime.utcnow()
        # Note: Keep is_active True until expiration for existing access

class SubscriptionPlan:
    """Subscription plan configuration"""
    
    PLANS = {
        SubscriptionTier.MONTHLY_PREMIUM.value: {
            "id": "monthly_premium",
            "name": "Monthly Premium",
            "description": "Full access to all premium features",
            "price_usd": 9.99,
            "currency": "USD",
            "period": "monthly",
            "duration_months": 1,
            "features": [
                "Unlimited tasks and reminders",
                "Advanced AI chat features",
                "Priority notifications",
                "Cloud sync across devices",
                "Advanced analytics",
                "Custom themes",
                "Export data",
                "Priority support"
            ],
            "product_ids": {
                "ios": "brain_dumpster_monthly_premium",
                "android": "brain_dumpster_monthly_premium",
                "revenuecat": "monthly_premium"
            }
        },
        SubscriptionTier.YEARLY_PREMIUM.value: {
            "id": "yearly_premium",
            "name": "Yearly Premium",
            "description": "Full access with 33% savings",
            "price_usd": 79.99,
            "currency": "USD",
            "period": "yearly",
            "duration_months": 12,
            "original_price": 119.88,
            "discount_percentage": 33,
            "is_popular": True,
            "features": [
                "Unlimited tasks and reminders",
                "Advanced AI chat features",
                "Priority notifications",
                "Cloud sync across devices",
                "Advanced analytics",
                "Custom themes",
                "Export data",
                "Priority support",
                "33% savings compared to monthly"
            ],
            "product_ids": {
                "ios": "brain_dumpster_yearly_premium",
                "android": "brain_dumpster_yearly_premium",
                "revenuecat": "yearly_premium"
            }
        },
        SubscriptionTier.LIFETIME_PREMIUM.value: {
            "id": "lifetime_premium",
            "name": "Lifetime Premium",
            "description": "One-time payment for lifetime access",
            "price_usd": 199.99,
            "currency": "USD",
            "period": "lifetime",
            "duration_months": None,
            "features": [
                "Unlimited tasks and reminders",
                "Advanced AI chat features",
                "Priority notifications",
                "Cloud sync across devices",
                "Advanced analytics",
                "Custom themes",
                "Export data",
                "Priority support",
                "Lifetime access - no recurring charges",
                "Future feature updates included"
            ],
            "product_ids": {
                "ios": "brain_dumpster_lifetime_premium",
                "android": "brain_dumpster_lifetime_premium",
                "revenuecat": "lifetime_premium"
            }
        }
    }

    # Regional pricing multipliers
    REGIONAL_PRICING = {
        "US": 1.0,    # Base price
        "GB": 0.9,    # 10% discount
        "EU": 1.0,    # Same as US
        "JP": 110,    # ~110 yen per dollar
        "IN": 75,     # ~75 rupees per dollar
        "BR": 5.0,    # ~5 reais per dollar
        "CN": 6.8,    # ~6.8 yuan per dollar
        "CA": 1.25,   # ~1.25 CAD per USD
        "AU": 1.35,   # ~1.35 AUD per USD
        "MX": 18.0,   # ~18 pesos per dollar
    }

    @classmethod
    def get_all_plans(cls) -> List[Dict]:
        """Get all available subscription plans"""
        return list(cls.PLANS.values())

    @classmethod
    def get_plan_by_id(cls, plan_id: str) -> Optional[Dict]:
        """Get plan by ID"""
        return cls.PLANS.get(plan_id)

    @classmethod
    def get_regional_price(cls, plan_id: str, region: str = "US") -> Optional[float]:
        """Get regional price for a plan"""
        plan = cls.get_plan_by_id(plan_id)
        if not plan:
            return None
        
        base_price = plan["price_usd"]
        multiplier = cls.REGIONAL_PRICING.get(region, 1.0)
        
        return base_price * multiplier

    @classmethod
    def get_all_regional_pricing(cls, plan_id: str) -> Dict[str, float]:
        """Get all regional pricing for a plan"""
        plan = cls.get_plan_by_id(plan_id)
        if not plan:
            return {}
        
        base_price = plan["price_usd"]
        regional_pricing = {}
        
        for region, multiplier in cls.REGIONAL_PRICING.items():
            regional_pricing[region] = round(base_price * multiplier, 2)
        
        return regional_pricing

class UserEntitlements:
    """User entitlements based on subscription"""
    
    def __init__(self, subscription: Optional[Subscription] = None):
        self.subscription = subscription
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict:
        """Convert entitlements to dictionary"""
        is_premium = self.subscription.is_premium() if self.subscription else False
        
        return {
            "is_premium": is_premium,
            "has_unlimited_tasks": is_premium,
            "has_advanced_ai": is_premium,
            "has_priority_notifications": is_premium,
            "has_cloud_sync": True,  # Basic cloud sync for all users
            "has_advanced_analytics": is_premium,
            "has_custom_themes": is_premium,
            "has_data_export": is_premium,
            "has_priority_support": is_premium,
            "last_updated": self.updated_at.isoformat()
        }

    def has_feature(self, feature: str) -> bool:
        """Check if user has access to a specific feature"""
        entitlements = self.to_dict()
        return entitlements.get(f"has_{feature}", False)

    @classmethod
    def get_free_entitlements(cls) -> Dict:
        """Get free tier entitlements"""
        return cls().to_dict()

    @classmethod
    def get_premium_entitlements(cls) -> Dict:
        """Get premium entitlements"""
        # Create a mock active subscription for premium entitlements
        mock_subscription = Subscription(
            user_id="mock",
            tier=SubscriptionTier.MONTHLY_PREMIUM.value,
            status=SubscriptionStatus.ACTIVE.value,
            expiration_date=datetime.utcnow() + timedelta(days=30)
        )
        return cls(mock_subscription).to_dict()