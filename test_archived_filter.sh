#!/bin/bash

echo "🧪 Testing Archived Tasks Filter"
echo "=================================="
echo ""

# Test 1: Health check
echo "1️⃣ Testing API health..."
health_response=$(curl -s https://api.braindumpster.io/api/health)
echo "Health check: ${health_response:0:100}..."
echo ""

# Test 2: Check if archived tasks are filtered
echo "2️⃣ Testing archived tasks filter..."
echo ""
echo "📝 Instructions:"
echo "   To fully test this, you need a Firebase auth token."
echo "   1. Open iOS app and sign in"
echo "   2. Get your user ID from Firebase Console"
echo "   3. Run this command with your token:"
echo ""
echo "   curl -X GET 'https://api.braindumpster.io/api/tasks/user/YOUR_USER_ID?status=completed' \\"
echo "        -H 'Authorization: Bearer YOUR_FIREBASE_TOKEN' \\"
echo "        -H 'Content-Type: application/json'"
echo ""
echo "   ✅ Expected: Completed tasks WITHOUT archived:true field"
echo "   ❌ Before fix: All completed tasks including archived ones"
echo ""

# Test 3: Check backend logs
echo "3️⃣ Backend should be filtering archived tasks..."
echo "   Check server logs for:"
echo "   - '🗄️ Filtering out archived task' messages"
echo "   - Task count before/after filtering"
echo ""

echo "=================================="
echo "✅ Setup complete!"
echo ""
echo "To get your Firebase auth token from iOS app:"
echo "1. Add a breakpoint in AuthService.swift getIdToken()"
echo "2. Copy the token from debugger"
echo "3. Use it in the curl command above"
