#!/usr/bin/env python3
"""
Direct test of Gemini API with test_audio.mp3
"""
import os
import sys
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini
api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    print("❌ GEMINI_API_KEY not found in environment")
    sys.exit(1)

genai.configure(api_key=api_key)

# Initialize model - Use Gemini 2.5 Flash (65K output tokens vs 8K for 2.0)
model = genai.GenerativeModel('gemini-2.5-flash')

# Load prompt from prompts/gemini_prompts.py
from prompts.gemini_prompts import MEETING_ANALYSIS_PROMPT

# Prepare prompt variables
current_date = datetime.now().strftime("%Y-%m-%d")
duration = 1438  # seconds (from previous tests)

# Format prompt
prompt = MEETING_ANALYSIS_PROMPT.format(
    current_date=current_date,
    duration=duration
)

print(f"📤 Uploading /home/ubuntu/test_audio.mp3 to Gemini...")

# Upload file to Gemini
audio_file = genai.upload_file(
    path="/home/ubuntu/test_audio.mp3",
    mime_type="audio/mpeg"
)

print(f"✅ File uploaded: {audio_file.name}")
print(f"⏳ Waiting for file to be processed...")

# Wait for file to be active
import time
while audio_file.state.name == "PROCESSING":
    time.sleep(2)
    audio_file = genai.get_file(audio_file.name)
    print(f"   Status: {audio_file.state.name}")

if audio_file.state.name != "ACTIVE":
    print(f"❌ File processing failed: {audio_file.state.name}")
    sys.exit(1)

print(f"✅ File is active, sending to Gemini...")

# Call Gemini with same config as service
generation_config = {
    "temperature": 0.4,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 65536,
}

print(f"🤖 Calling Gemini with config: {generation_config}")

response = model.generate_content(
    [prompt, audio_file],
    generation_config=generation_config
)

print(f"\n✅ Response received!")
print(f"📏 Response length: {len(response.text)} chars")

# Check finish_reason
if hasattr(response, 'candidates') and response.candidates:
    candidate = response.candidates[0]
    print(f"⚠️  finish_reason: {candidate.finish_reason}")

    if hasattr(candidate, 'safety_ratings'):
        print(f"🛡️  safety_ratings: {candidate.safety_ratings}")

# Save response to file
output_file = "/tmp/test_gemini_response.txt"
with open(output_file, 'w') as f:
    f.write(response.text)

print(f"\n💾 Full response saved to: {output_file}")
print(f"\n📝 First 500 chars:")
print(response.text[:500])
print(f"\n📝 Last 500 chars:")
print(response.text[-500:])

# Check if response ends properly
if response.text.strip().endswith('```'):
    print(f"\n✅ Response ends with ``` (complete)")
else:
    print(f"\n⚠️  Response does NOT end with ``` (may be truncated)")
    print(f"   Last 100 chars: {repr(response.text[-100:])}")

# Clean up
genai.delete_file(audio_file.name)
print(f"\n🗑️  Deleted uploaded file from Gemini")
