#!/usr/bin/env python3

from services.firebase_service import FirebaseService
from collections import defaultdict
import json

def analyze_subscriptions():
    firebase = FirebaseService()

    # Tüm subscription'ları al
    db = firebase.db
    subscriptions_ref = db.collection('subscriptions')
    docs = subscriptions_ref.stream()

    subscriptions = []
    for doc in docs:
        data = doc.to_dict()
        subscriptions.append(data)

    print('🔍 SUBSCRIPTION ANALYTICS')
    print('=' * 50)

    # Genel istatistikler
    total_subs = len(subscriptions)
    active_subs = sum(1 for s in subscriptions if s.get('is_active', False))
    premium_users = sum(1 for s in subscriptions if s.get('is_premium', False))

    print(f'📊 GENEL İSTATİSTİKLER:')
    print(f'   Toplam Abonelik: {total_subs}')
    print(f'   Aktif Abonelikler: {active_subs}')
    print(f'   Premium Kullanıcılar: {premium_users}')
    print(f'   Aktiflik Oranı: {(active_subs/total_subs*100):.1f}%' if total_subs > 0 else '   Aktiflik Oranı: 0%')
    print()

    # Tier bazında analiz
    tier_stats = defaultdict(int)
    tier_active = defaultdict(int)
    for sub in subscriptions:
        tier = sub.get('tier', 'unknown')
        tier_stats[tier] += 1
        if sub.get('is_active', False):
            tier_active[tier] += 1

    print(f'📈 TİER BAZINDA ANALİZ:')
    for tier, count in tier_stats.items():
        active_count = tier_active[tier]
        percentage = (active_count/count*100) if count > 0 else 0
        print(f'   {tier}: {count} total, {active_count} aktif ({percentage:.1f}%)')
    print()

    # Platform bazında analiz
    platform_stats = defaultdict(int)
    for sub in subscriptions:
        platform = sub.get('platform', 'unknown')
        if sub.get('is_active', False):
            platform_stats[platform] += 1

    print(f'📱 PLATFORM BAZINDA ANALİZ (Aktif):')
    for platform, count in platform_stats.items():
        print(f'   {platform}: {count} aktif kullanıcı')
    print()

    # Status bazında analiz
    status_stats = defaultdict(int)
    for sub in subscriptions:
        status = sub.get('status', 'unknown')
        status_stats[status] += 1

    print(f'⚡ STATUS BAZINDA ANALİZ:')
    for status, count in status_stats.items():
        print(f'   {status}: {count} kullanıcı')
    print()

    # Detaylı kullanıcı listesi
    print(f'👥 DETAYLI KULLANICI LİSTESİ:')
    print('-' * 80)
    for i, sub in enumerate(subscriptions, 1):
        user_id = sub.get('user_id', 'unknown')[:20]  # İlk 20 karakter
        tier = sub.get('tier', 'N/A')
        status = sub.get('status', 'N/A')
        platform = sub.get('platform', 'N/A')
        expiration = sub.get('expiration_date', 'N/A')
        if expiration and expiration != 'N/A' and len(str(expiration)) > 10:
            expiration = str(expiration)[:10]  # Sadece tarih kısmı
        elif not expiration:
            expiration = 'Lifetime'

        status_emoji = '✅' if sub.get('is_active') else '❌'
        premium_emoji = '👑' if sub.get('is_premium') else '🆓'

        print(f'{i:2d}. {status_emoji} {premium_emoji} {user_id:<20} | {tier:<17} | {status:<9} | {platform:<12} | {expiration}')

    print('-' * 80)
    print(f'Total: {len(subscriptions)} subscribers')

if __name__ == '__main__':
    analyze_subscriptions()