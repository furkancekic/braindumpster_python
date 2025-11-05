#!/usr/bin/env python3
"""
Test script for meeting recording analysis endpoint
Creates a simple audio file and sends it to the API
"""

import requests
import json
import wave
import struct
import math
import os

def create_test_audio(filename="test_audio.wav", duration=5):
    """Create a simple sine wave audio file for testing"""
    print(f"🎵 Creating test audio file: {filename} ({duration}s)")

    # Audio parameters
    sample_rate = 44100
    num_channels = 1
    sample_width = 2  # 16-bit

    # Create WAV file
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(num_channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)

        # Generate sine wave (440 Hz - A note)
        for i in range(int(duration * sample_rate)):
            value = int(32767.0 * math.sin(2.0 * math.pi * 440.0 * i / sample_rate))
            data = struct.pack('<h', value)
            wav_file.writeframes(data)

    print(f"✅ Created {filename} ({os.path.getsize(filename)} bytes)")
    return filename

def test_analyze_endpoint(audio_file, api_url="http://localhost:8000", token=None):
    """Test the /api/meetings/analyze endpoint"""

    endpoint = f"{api_url}/api/meetings/analyze"

    print(f"\n📤 Testing endpoint: {endpoint}")
    print(f"   Audio file: {audio_file}")

    # Prepare multipart form data
    with open(audio_file, 'rb') as f:
        files = {
            'audio': (os.path.basename(audio_file), f, 'audio/wav')
        }
        data = {
            'duration': 5  # 5 seconds
        }

        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            print("⏳ Sending request...")
            response = requests.post(
                endpoint,
                files=files,
                data=data,
                headers=headers,
                timeout=300  # 5 minutes
            )

            print(f"\n📊 Response Status: {response.status_code}")
            print(f"📊 Response Headers: {dict(response.headers)}")

            if response.status_code == 200:
                result = response.json()
                print(f"\n✅ SUCCESS!")
                print(f"   Recording ID: {result.get('recordingId')}")
                print(f"   Title: {result.get('recording', {}).get('title')}")
                print(f"   Type: {result.get('recording', {}).get('type')}")
                print(f"\n📝 Full Response:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"\n❌ FAILED!")
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text}")

                try:
                    error_data = response.json()
                    if 'traceback' in error_data:
                        print(f"\n🔴 Backend Traceback:")
                        print(error_data['traceback'])
                except:
                    pass

        except requests.Timeout:
            print("❌ Request timed out after 5 minutes")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()

def main():
    print("=" * 80)
    print("🧪 MEETING RECORDER API TEST")
    print("=" * 80)

    # Create test audio
    audio_file = create_test_audio(duration=5)

    # Test without authentication (should return 401)
    print("\n\n📍 Test 1: Without Authentication")
    print("-" * 80)
    test_analyze_endpoint(audio_file)

    # Test with authentication (requires valid Firebase token)
    print("\n\n📍 Test 2: With Authentication (if token provided)")
    print("-" * 80)
    token = os.environ.get('FIREBASE_TOKEN')
    if token:
        test_analyze_endpoint(audio_file, token=token)
    else:
        print("⏭️  Skipping (no FIREBASE_TOKEN env var)")
        print("   To test with auth: export FIREBASE_TOKEN='your_token_here'")

    # Cleanup
    if os.path.exists(audio_file):
        os.remove(audio_file)
        print(f"\n🧹 Cleaned up {audio_file}")

    print("\n" + "=" * 80)
    print("✅ Test completed!")
    print("=" * 80)

if __name__ == "__main__":
    main()
