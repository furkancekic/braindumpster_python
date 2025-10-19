import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import json
from functools import lru_cache

logger = logging.getLogger(__name__)

class RegionalPricingService:
    """Service for handling regional pricing and currency conversion"""
    
    # Exchange rate API (using exchangerate-api.com as example)
    EXCHANGE_RATE_API_URL = "https://api.exchangerate-api.com/v4/latest/USD"
    
    # Regional pricing strategies
    PRICING_STRATEGIES = {
        # Developed markets - standard pricing
        'US': {'multiplier': 1.0, 'currency': 'USD', 'strategy': 'standard'},
        'CA': {'multiplier': 1.35, 'currency': 'CAD', 'strategy': 'standard'},
        'GB': {'multiplier': 0.85, 'currency': 'GBP', 'strategy': 'standard'},
        'AU': {'multiplier': 1.45, 'currency': 'AUD', 'strategy': 'standard'},
        'DE': {'multiplier': 0.92, 'currency': 'EUR', 'strategy': 'standard'},
        'FR': {'multiplier': 0.92, 'currency': 'EUR', 'strategy': 'standard'},
        'IT': {'multiplier': 0.92, 'currency': 'EUR', 'strategy': 'standard'},
        'ES': {'multiplier': 0.92, 'currency': 'EUR', 'strategy': 'standard'},
        'NL': {'multiplier': 0.92, 'currency': 'EUR', 'strategy': 'standard'},
        'SE': {'multiplier': 10.5, 'currency': 'SEK', 'strategy': 'standard'},
        'NO': {'multiplier': 10.8, 'currency': 'NOK', 'strategy': 'standard'},
        'DK': {'multiplier': 6.8, 'currency': 'DKK', 'strategy': 'standard'},
        'CH': {'multiplier': 0.95, 'currency': 'CHF', 'strategy': 'premium'},  # Higher prices for Switzerland
        'JP': {'multiplier': 145.0, 'currency': 'JPY', 'strategy': 'standard'},
        'KR': {'multiplier': 1300.0, 'currency': 'KRW', 'strategy': 'standard'},
        'SG': {'multiplier': 1.4, 'currency': 'SGD', 'strategy': 'standard'},
        'HK': {'multiplier': 7.8, 'currency': 'HKD', 'strategy': 'standard'},
        'NZ': {'multiplier': 1.6, 'currency': 'NZD', 'strategy': 'standard'},
        
        # Emerging markets - purchasing power parity adjusted
        'IN': {'multiplier': 75.0, 'currency': 'INR', 'strategy': 'ppp_adjusted', 'discount': 0.6},
        'BR': {'multiplier': 5.2, 'currency': 'BRL', 'strategy': 'ppp_adjusted', 'discount': 0.7},
        'MX': {'multiplier': 18.0, 'currency': 'MXN', 'strategy': 'ppp_adjusted', 'discount': 0.8},
        'AR': {'multiplier': 350.0, 'currency': 'ARS', 'strategy': 'ppp_adjusted', 'discount': 0.5},
        'CO': {'multiplier': 4200.0, 'currency': 'COP', 'strategy': 'ppp_adjusted', 'discount': 0.7},
        'CL': {'multiplier': 900.0, 'currency': 'CLP', 'strategy': 'ppp_adjusted', 'discount': 0.8},
        'PE': {'multiplier': 3.8, 'currency': 'PEN', 'strategy': 'ppp_adjusted', 'discount': 0.7},
        'TR': {'multiplier': 28.0, 'currency': 'TRY', 'strategy': 'ppp_adjusted', 'discount': 0.6},
        'RU': {'multiplier': 75.0, 'currency': 'RUB', 'strategy': 'ppp_adjusted', 'discount': 0.5},
        'CN': {'multiplier': 7.2, 'currency': 'CNY', 'strategy': 'ppp_adjusted', 'discount': 0.8},
        'TH': {'multiplier': 35.0, 'currency': 'THB', 'strategy': 'ppp_adjusted', 'discount': 0.7},
        'VN': {'multiplier': 24000.0, 'currency': 'VND', 'strategy': 'ppp_adjusted', 'discount': 0.6},
        'ID': {'multiplier': 15000.0, 'currency': 'IDR', 'strategy': 'ppp_adjusted', 'discount': 0.6},
        'MY': {'multiplier': 4.5, 'currency': 'MYR', 'strategy': 'ppp_adjusted', 'discount': 0.7},
        'PH': {'multiplier': 55.0, 'currency': 'PHP', 'strategy': 'ppp_adjusted', 'discount': 0.6},
        'EG': {'multiplier': 30.0, 'currency': 'EGP', 'strategy': 'ppp_adjusted', 'discount': 0.5},
        'ZA': {'multiplier': 18.0, 'currency': 'ZAR', 'strategy': 'ppp_adjusted', 'discount': 0.6},
        'NG': {'multiplier': 800.0, 'currency': 'NGN', 'strategy': 'ppp_adjusted', 'discount': 0.4},
        'KE': {'multiplier': 130.0, 'currency': 'KES', 'strategy': 'ppp_adjusted', 'discount': 0.5},
        'UA': {'multiplier': 37.0, 'currency': 'UAH', 'strategy': 'ppp_adjusted', 'discount': 0.4},
        'PL': {'multiplier': 4.3, 'currency': 'PLN', 'strategy': 'ppp_adjusted', 'discount': 0.8},
        'CZ': {'multiplier': 23.0, 'currency': 'CZK', 'strategy': 'ppp_adjusted', 'discount': 0.8},
        'HU': {'multiplier': 380.0, 'currency': 'HUF', 'strategy': 'ppp_adjusted', 'discount': 0.7},
        'RO': {'multiplier': 4.9, 'currency': 'RON', 'strategy': 'ppp_adjusted', 'discount': 0.7},
    }
    
    def __init__(self):
        self._exchange_rates_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = timedelta(hours=6)  # Cache exchange rates for 6 hours
    
    def get_regional_pricing(self, base_price_usd: float, country_code: str) -> Dict:
        """Get regional pricing for a product in a specific country"""
        logger.info(f"Getting regional pricing for {country_code}: ${base_price_usd}")
        
        country_code = country_code.upper()
        pricing_info = self.PRICING_STRATEGIES.get(country_code)
        
        if not pricing_info:
            # Default to US pricing for unknown countries
            logger.warning(f"No pricing strategy found for {country_code}, using US default")
            pricing_info = self.PRICING_STRATEGIES['US']
            country_code = 'US'
        
        strategy = pricing_info['strategy']
        currency = pricing_info['currency']
        multiplier = pricing_info['multiplier']
        
        # Calculate base price in local currency
        local_price = base_price_usd * multiplier
        
        # Apply strategy-specific adjustments
        if strategy == 'ppp_adjusted':
            # Apply purchasing power parity discount
            discount = pricing_info.get('discount', 1.0)
            local_price = local_price * discount
            
        elif strategy == 'premium':
            # Apply premium pricing (10% increase)
            local_price = local_price * 1.1
        
        # Round to appropriate precision based on currency
        local_price = self._round_price(local_price, currency)
        
        # Calculate savings compared to US price in local currency
        us_price_in_local = base_price_usd * multiplier
        savings_amount = us_price_in_local - local_price if local_price < us_price_in_local else 0
        savings_percentage = int((savings_amount / us_price_in_local) * 100) if us_price_in_local > 0 else 0
        
        result = {
            'country_code': country_code,
            'currency': currency,
            'price': local_price,
            'original_price_usd': base_price_usd,
            'exchange_rate': multiplier,
            'strategy': strategy,
            'savings': {
                'amount': self._round_price(savings_amount, currency) if savings_amount > 0 else 0,
                'percentage': savings_percentage
            },
            'formatted_price': self._format_price(local_price, currency)
        }
        
        logger.info(f"Regional pricing calculated: {result}")
        return result
    
    def get_all_regional_pricing(self, base_price_usd: float) -> Dict[str, Dict]:
        """Get pricing for all supported regions"""
        logger.info(f"Getting pricing for all regions: ${base_price_usd}")
        
        regional_prices = {}
        
        for country_code in self.PRICING_STRATEGIES.keys():
            regional_prices[country_code] = self.get_regional_pricing(base_price_usd, country_code)
        
        return regional_prices
    
    def detect_user_region(self, ip_address: str = None, user_agent: str = None) -> str:
        """Detect user's region based on IP address or other signals"""
        # TODO(context7): Implement IP geolocation service integration
        # For now, return US as default
        logger.info(f"Detecting region for IP: {ip_address}")
        
        if ip_address:
            try:
                # Example using a free IP geolocation service
                # response = requests.get(f"http://ip-api.com/json/{ip_address}")
                # if response.status_code == 200:
                #     data = response.json()
                #     return data.get('countryCode', 'US')
                pass
            except Exception as e:
                logger.error(f"Failed to detect region: {e}")
        
        return 'US'  # Default to US
    
    @lru_cache(maxsize=100)
    def get_supported_countries(self) -> List[str]:
        """Get list of supported country codes"""
        return list(self.PRICING_STRATEGIES.keys())
    
    def get_currency_symbol(self, currency_code: str) -> str:
        """Get currency symbol for display"""
        symbols = {
            'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥', 'CNY': '¥',
            'INR': '₹', 'KRW': '₩', 'BRL': 'R$', 'CAD': 'C$', 'AUD': 'A$',
            'CHF': 'Fr', 'SEK': 'kr', 'NOK': 'kr', 'DKK': 'kr',
            'RUB': '₽', 'TRY': '₺', 'MXN': '$', 'ARS': '$',
            'COP': '$', 'CLP': '$', 'PEN': 'S/', 'THB': '฿',
            'VND': '₫', 'IDR': 'Rp', 'MYR': 'RM', 'PHP': '₱',
            'SGD': 'S$', 'HKD': 'HK$', 'NZD': 'NZ$', 'ZAR': 'R',
            'EGP': 'E£', 'NGN': '₦', 'KES': 'KSh', 'UAH': '₴',
            'PLN': 'zł', 'CZK': 'Kč', 'HUF': 'Ft', 'RON': 'lei'
        }
        return symbols.get(currency_code.upper(), currency_code)
    
    def _round_price(self, price: float, currency: str) -> float:
        """Round price appropriately based on currency"""
        # For currencies with no decimal places
        if currency in ['JPY', 'KRW', 'VND', 'IDR', 'CLP', 'COP', 'HUF', 'NGN', 'KES']:
            return round(price)
        
        # For most currencies, round to 2 decimal places
        return round(price, 2)
    
    def _format_price(self, price: float, currency: str) -> str:
        """Format price with currency symbol"""
        symbol = self.get_currency_symbol(currency)
        
        # Format based on currency
        if currency in ['JPY', 'KRW', 'VND', 'IDR', 'CLP', 'COP', 'HUF', 'NGN', 'KES']:
            return f"{symbol}{int(price):,}"
        else:
            return f"{symbol}{price:,.2f}"
    
    def get_pricing_strategy_info(self, country_code: str) -> Dict:
        """Get detailed pricing strategy information for a country"""
        country_code = country_code.upper()
        strategy_info = self.PRICING_STRATEGIES.get(country_code, self.PRICING_STRATEGIES['US'])
        
        return {
            'country_code': country_code,
            'currency': strategy_info['currency'],
            'strategy': strategy_info['strategy'],
            'multiplier': strategy_info['multiplier'],
            'discount': strategy_info.get('discount'),
            'currency_symbol': self.get_currency_symbol(strategy_info['currency'])
        }
    
    def validate_country_code(self, country_code: str) -> bool:
        """Validate if a country code is supported"""
        return country_code.upper() in self.PRICING_STRATEGIES
    
    def get_price_comparison(self, base_price_usd: float, country_codes: List[str]) -> Dict:
        """Compare prices across multiple countries"""
        logger.info(f"Comparing prices across countries: {country_codes}")
        
        comparison = {
            'base_price_usd': base_price_usd,
            'countries': {},
            'cheapest': None,
            'most_expensive': None
        }
        
        min_price_usd = float('inf')
        max_price_usd = 0
        
        for country_code in country_codes:
            if not self.validate_country_code(country_code):
                continue
                
            pricing = self.get_regional_pricing(base_price_usd, country_code)
            
            # Convert back to USD for comparison
            usd_equivalent = pricing['price'] / pricing['exchange_rate']
            
            comparison['countries'][country_code] = {
                **pricing,
                'usd_equivalent': round(usd_equivalent, 2)
            }
            
            if usd_equivalent < min_price_usd:
                min_price_usd = usd_equivalent
                comparison['cheapest'] = country_code
            
            if usd_equivalent > max_price_usd:
                max_price_usd = usd_equivalent
                comparison['most_expensive'] = country_code
        
        return comparison
    
    def get_subscription_tier_regional_pricing(self, subscription_plans: List[Dict]) -> Dict:
        """Get regional pricing for all subscription tiers"""
        logger.info("Getting regional pricing for all subscription tiers")
        
        regional_tiers = {}
        
        for plan in subscription_plans:
            plan_id = plan['id']
            base_price = plan['price_usd']
            
            regional_tiers[plan_id] = self.get_all_regional_pricing(base_price)
        
        return regional_tiers