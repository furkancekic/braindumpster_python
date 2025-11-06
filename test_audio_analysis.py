#!/usr/bin/env python3
"""
Test script to analyze audio file with Gemini API
"""
import sys
import os
import time
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_audio_analysis(audio_file_path):
    """Test audio analysis with Gemini API"""

    # Configure Gemini
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY not found in .env file")
        sys.exit(1)

    genai.configure(api_key=api_key)

    # Check file
    if not os.path.exists(audio_file_path):
        print(f"❌ File not found: {audio_file_path}")
        sys.exit(1)

    file_size_mb = os.path.getsize(audio_file_path) / (1024 * 1024)
    print(f"📁 File: {os.path.basename(audio_file_path)}")
    print(f"📊 Size: {file_size_mb:.2f} MB")
    print()

    # Detect MIME type
    file_extension = os.path.splitext(audio_file_path)[1].lower()
    mime_types = {
        '.mp3': 'audio/mpeg',
        '.m4a': 'audio/mp4',
        '.wav': 'audio/wav',
        '.aac': 'audio/aac'
    }
    mime_type = mime_types.get(file_extension, 'audio/mp4')
    print(f"🎵 MIME Type: {mime_type}")
    print()

    # Create models to test (without -latest suffix for v1beta API)
    models_to_test = [
        'gemini-1.5-pro',
        'gemini-1.5-flash',
        'gemini-2.0-flash-exp'
    ]

    for model_name in models_to_test:
        print(f"\n{'='*80}")
        print(f"🧪 Testing with: {model_name}")
        print(f"{'='*80}\n")

        try:
            model = genai.GenerativeModel(model_name)

            # Use File API for large files
            if file_size_mb > 10:
                print(f"📤 Uploading file to Gemini File API...")
                uploaded_file = genai.upload_file(path=audio_file_path, mime_type=mime_type)
                print(f"✅ File uploaded: {uploaded_file.name}")
                print(f"   URI: {uploaded_file.uri}")
                print(f"   State: {uploaded_file.state.name}")

                # Wait for processing
                while uploaded_file.state.name == "PROCESSING":
                    print("⏳ Waiting for file processing...")
                    time.sleep(2)
                    uploaded_file = genai.get_file(uploaded_file.name)

                if uploaded_file.state.name == "FAILED":
                    print(f"❌ File processing failed!")
                    continue

                print(f"✅ File ready for analysis")
                print()

                # Create prompt
                prompt = """Bu ses kaydını analiz et ve şu bilgileri çıkar:

1. Konuşmacı sayısı
2. Ana konular (3-5 madde)
3. Kısa özet (2-3 cümle)
4. Konuşulan dil

Lütfen sadece bu bilgileri Türkçe olarak ver."""

                print("🤖 Sending to Gemini for analysis...")

                # Generate with config
                generation_config = {
                    "temperature": 0.4,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                }

                response = model.generate_content(
                    [prompt, uploaded_file],
                    generation_config=generation_config
                )

                print(f"✅ Analysis complete!")
                print()
                print("=" * 80)
                print("📝 RESPONSE:")
                print("=" * 80)
                print(response.text)
                print()

                # Cleanup
                print(f"🗑️  Deleting file from Gemini...")
                genai.delete_file(uploaded_file.name)
                print(f"✅ File deleted")

            else:
                # Use inline data for small files
                print(f"📦 Using inline data for small file...")
                import base64

                with open(audio_file_path, 'rb') as f:
                    audio_data = f.read()

                audio_part = {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64.b64encode(audio_data).decode("utf-8")
                    }
                }

                prompt = """Bu ses kaydını analiz et ve şu bilgileri çıkar:

1. Konuşmacı sayısı
2. Ana konular (3-5 madde)
3. Kısa özet (2-3 cümle)
4. Konuşulan dil

Lütfen sadece bu bilgileri Türkçe olarak ver."""

                print("🤖 Sending to Gemini for analysis...")

                generation_config = {
                    "temperature": 0.4,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                }

                response = model.generate_content(
                    [prompt, audio_part],
                    generation_config=generation_config
                )

                print(f"✅ Analysis complete!")
                print()
                print("=" * 80)
                print("📝 RESPONSE:")
                print("=" * 80)
                print(response.text)
                print()

        except Exception as e:
            print(f"❌ Error with {model_name}:")
            print(f"   {str(e)}")
            import traceback
            print(traceback.format_exc())
            continue

if __name__ == "__main__":
    # Test file path
    test_file = "/Users/furkancekic/Downloads/Yaşlıları Ne Yapalım_- Her Şeyin Ekonomisi - Prof. Aylin Seçkin Georges - B06.mp3"

    print("🎤 Audio Analysis Test Script")
    print("=" * 80)
    print()

    test_audio_analysis(test_file)

    print("\n✅ Test completed!")
