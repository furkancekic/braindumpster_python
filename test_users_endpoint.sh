#!/bin/bash

# Test script for users endpoint
# Tests if /api/users/me endpoint is registered and accessible

echo "🧪 Testing Users Endpoint Registration..."
echo "=========================================="
echo ""

# Test 1: Health check
echo "1️⃣ Testing health endpoint..."
curl -s https://api.braindumpster.io/api/health | head -c 100
echo ""
echo ""

# Test 2: Check if endpoint returns 401 (not 404) without auth
echo "2️⃣ Testing /api/users/me without authentication..."
echo "   Expected: 401 Unauthorized (endpoint exists)"
echo "   If 404: endpoint not registered (backend needs restart)"
echo ""

response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X DELETE https://api.braindumpster.io/api/users/me)
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | grep -v "HTTP_CODE")

echo "   Response body: $body"
echo "   HTTP Status Code: $http_code"
echo ""

if [ "$http_code" = "401" ]; then
    echo "   ✅ SUCCESS! Endpoint is registered (returns 401 without auth)"
    echo "   Backend has been restarted correctly!"
elif [ "$http_code" = "404" ]; then
    echo "   ❌ FAILED! Endpoint not found (404)"
    echo "   Backend needs to be restarted!"
    echo ""
    echo "   🔧 Fix this by running on your server:"
    echo "      cd /path/to/braindumpster_python"
    echo "      git pull origin main"
    echo "      sudo systemctl restart braindumpster-api"
else
    echo "   ⚠️  Unexpected status code: $http_code"
fi

echo ""
echo "=========================================="
