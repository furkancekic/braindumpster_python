#!/usr/bin/env python3
"""
Test Progressive Loading for Audio Analysis
Tests the 3-stage progressive approach: transcription → quick analysis → deep analysis
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.gemini_service import GeminiService

def test_progressive_loading(audio_file_path: str):
    """Test the 3-stage progressive loading"""

    print("=" * 80)
    print("🧪 PROGRESSIVE LOADING TEST")
    print("=" * 80)
    print(f"📁 Audio file: {audio_file_path}")
    print()

    # Initialize service
    print("🔧 Initializing GeminiService...")
    gemini_service = GeminiService()
    print("✅ GeminiService initialized\n")

    # Read audio file
    print("📂 Reading audio file...")
    with open(audio_file_path, 'rb') as f:
        audio_data = f.read()

    file_size_mb = len(audio_data) / (1024 * 1024)
    print(f"✅ Audio loaded: {file_size_mb:.2f} MB\n")

    # Detect MIME type
    if audio_file_path.endswith('.mp3'):
        mime_type = 'audio/mpeg'
    elif audio_file_path.endswith('.m4a'):
        mime_type = 'audio/mp4'
    elif audio_file_path.endswith('.wav'):
        mime_type = 'audio/wav'
    else:
        mime_type = 'audio/mp4'

    print(f"🎵 MIME type: {mime_type}\n")

    current_date = datetime.now().strftime("%B %d, %Y")
    duration = 1438  # seconds (adjust based on your audio)

    # ========== STAGE 1: TRANSCRIPTION ==========
    print("=" * 80)
    print("📝 STAGE 1: TRANSCRIPTION")
    print("=" * 80)

    start_time = time.time()

    transcription_result = gemini_service.transcribe_audio_file(
        audio_data=audio_data,
        duration=duration,
        current_date=current_date,
        mime_type=mime_type
    )

    stage1_duration = time.time() - start_time

    if not transcription_result.get('success'):
        print(f"❌ Stage 1 FAILED: {transcription_result.get('error')}")
        return False

    transcription_data = transcription_result.get('transcription', {})
    transcript_text = transcription_data.get('transcriptText', '')
    transcript_segments = transcription_data.get('transcript', [])
    detected_language = transcription_data.get('language', 'unknown')
    speaker_count = transcription_data.get('speakerCount', 0)

    print(f"✅ STAGE 1 COMPLETE in {stage1_duration:.1f}s")
    print(f"   Language: {detected_language}")
    print(f"   Speakers: {speaker_count}")
    print(f"   Transcript length: {len(transcript_text)} chars")
    print(f"   Segments: {len(transcript_segments)}")
    print(f"\n📝 First 200 chars of transcript:")
    print(f"   {transcript_text[:200]}...")
    print()

    # ========== STAGE 2: QUICK ANALYSIS ==========
    print("=" * 80)
    print("⚡ STAGE 2: QUICK ANALYSIS")
    print("=" * 80)

    start_time = time.time()

    quick_analysis_result = gemini_service.quick_analyze_transcript(
        transcript_text=transcript_text,
        language=detected_language,
        current_date=current_date
    )

    stage2_duration = time.time() - start_time

    if not quick_analysis_result.get('success'):
        print(f"❌ Stage 2 FAILED: {quick_analysis_result.get('error')}")
        print("⚠️  Continuing with transcript only...")
    else:
        quick_analysis = quick_analysis_result.get('analysis', {})
        metadata = quick_analysis.get('metadata', {})
        summary = quick_analysis.get('summary', {})
        action_items = quick_analysis.get('actionItems', [])

        print(f"✅ STAGE 2 COMPLETE in {stage2_duration:.1f}s")
        print(f"   Type: {metadata.get('detectedType', 'unknown')}")
        print(f"   Title: {metadata.get('suggestedTitle', 'N/A')}")
        print(f"   Confidence: {metadata.get('confidence', 0):.2f}")
        print(f"   Action items: {len(action_items)}")
        print(f"\n💡 Brief summary:")
        print(f"   {summary.get('brief', 'N/A')}")
        print()

    # ========== STAGE 3: DEEP ANALYSIS ==========
    print("=" * 80)
    print("🔍 STAGE 3: DEEP ANALYSIS")
    print("=" * 80)

    start_time = time.time()

    deep_analysis_result = gemini_service.deep_analyze_transcript(
        transcript_text=transcript_text,
        language=detected_language,
        recording_type=metadata.get('detectedType', 'personal'),
        current_date=current_date
    )

    stage3_duration = time.time() - start_time

    if not deep_analysis_result.get('success'):
        print(f"❌ Stage 3 FAILED: {deep_analysis_result.get('error')}")
        print("⚠️  User still has transcript and quick analysis")
    else:
        deep_analysis = deep_analysis_result.get('analysis', {})
        key_points = deep_analysis.get('keyPoints', [])
        decisions = deep_analysis.get('decisions', [])
        sentiment = deep_analysis.get('sentiment', {})
        topics = deep_analysis.get('topics', [])

        print(f"✅ STAGE 3 COMPLETE in {stage3_duration:.1f}s")
        print(f"   Key points: {len(key_points)}")
        print(f"   Decisions: {len(decisions)}")
        print(f"   Topics: {len(topics)}")
        print(f"   Sentiment: {sentiment.get('overall', 'N/A')}")
        print()

    # ========== SUMMARY ==========
    total_time = stage1_duration + stage2_duration + stage3_duration

    print("=" * 80)
    print("📊 PERFORMANCE SUMMARY")
    print("=" * 80)
    print(f"Stage 1 (Transcription):  {stage1_duration:>6.1f}s  ({stage1_duration/total_time*100:.1f}%)")
    print(f"Stage 2 (Quick Analysis): {stage2_duration:>6.1f}s  ({stage2_duration/total_time*100:.1f}%)")
    print(f"Stage 3 (Deep Analysis):  {stage3_duration:>6.1f}s  ({stage3_duration/total_time*100:.1f}%)")
    print(f"─" * 80)
    print(f"TOTAL TIME:               {total_time:>6.1f}s")
    print()

    print("✅ Progressive loading test COMPLETE!")
    print()

    # User experience timeline
    print("👤 USER EXPERIENCE TIMELINE:")
    print(f"   At {stage1_duration:.0f}s: User sees TRANSCRIPT")
    print(f"   At {stage1_duration + stage2_duration:.0f}s: User sees SUMMARY + ACTION ITEMS")
    print(f"   At {total_time:.0f}s: User sees FULL ANALYSIS")
    print()

    return True


if __name__ == "__main__":
    # Check for audio file argument
    if len(sys.argv) < 2:
        print("Usage: python3 test_progressive_loading.py <audio_file_path>")
        print("\nExample:")
        print("  python3 test_progressive_loading.py /path/to/test_audio.mp3")
        sys.exit(1)

    audio_file = sys.argv[1]

    if not os.path.exists(audio_file):
        print(f"❌ Audio file not found: {audio_file}")
        sys.exit(1)

    success = test_progressive_loading(audio_file)

    sys.exit(0 if success else 1)
