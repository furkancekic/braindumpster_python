"""
PDF Generator Service
Generates professional meeting reports in PDF format using WeasyPrint
"""

import os
import re
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML, CSS
import logging

logger = logging.getLogger(__name__)


class PDFGeneratorService:
    """Service for generating PDF reports from meeting recordings"""

    def __init__(self):
        # Setup Jinja2 environment
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

        # Setup paths
        self.static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
        self.css_path = os.path.join(template_dir, 'pdf', 'styles.css')

        # PDF storage directory
        self.pdf_storage_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pdf_storage')
        os.makedirs(self.pdf_storage_dir, exist_ok=True)

        logger.info("✅ PDFGeneratorService initialized")

    def detect_language(self, recording_data: Dict[str, Any]) -> str:
        """
        Detect the language of the recording from the analysis data.

        Returns language code: 'tr' for Turkish, 'en' for English, etc.
        """
        try:
            # Check if language is explicitly stored
            if 'detected_language' in recording_data:
                return recording_data['detected_language']

            # Try to detect from content
            summary = recording_data.get('summary', {})

            # Check transcript for Turkish characters
            full_transcript = summary.get('fullTranscript', [])
            if full_transcript:
                # Sample some text from transcript
                sample_text = ' '.join([entry.get('text', '')[:100] for entry in full_transcript[:3]])

                # Turkish character detection
                turkish_chars = set('ıİğĞüÜşŞöÖçÇ')
                if any(char in sample_text for char in turkish_chars):
                    logger.info("📝 Detected Turkish language from transcript")
                    return 'tr'

            # Check brief/detailed summary
            brief = summary.get('brief', '')
            detailed = summary.get('detailed', '')
            combined_text = brief + ' ' + detailed

            turkish_chars = set('ıİğĞüÜşŞöÖçÇ')
            if any(char in combined_text for char in turkish_chars):
                logger.info("📝 Detected Turkish language from summary")
                return 'tr'

            # Default to English if no Turkish characters found
            logger.info("📝 Defaulting to English language")
            return 'en'

        except Exception as e:
            logger.warning(f"⚠️ Error detecting language: {e}, defaulting to 'en'")
            return 'en'

    def sanitize_filename(self, filename: str, language: str = 'en') -> str:
        """
        Sanitize filename for safe download.

        Only removes Turkish characters if the language is NOT Turkish.

        Args:
            filename: Original filename
            language: Detected language code ('tr', 'en', etc.)

        Returns:
            Sanitized filename safe for all systems
        """
        # Only apply Turkish character replacement if NOT Turkish
        if language != 'tr':
            # Remove Turkish characters for non-Turkish content
            replacements = {
                'ı': 'i', 'İ': 'I', 'ş': 's', 'Ş': 'S',
                'ğ': 'g', 'Ğ': 'G', 'ü': 'u', 'Ü': 'U',
                'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'
            }
            for old, new in replacements.items():
                filename = filename.replace(old, new)

            logger.info(f"📝 Applied Turkish character sanitization for {language} language")
        else:
            logger.info(f"📝 Keeping Turkish characters for Turkish language content")

        # Keep only alphanumeric, spaces, dashes, underscores
        # For Turkish, this preserves Turkish letters
        if language == 'tr':
            # Allow Turkish characters in regex
            filename = re.sub(r'[^\w\s\-ığüşöçĞÜŞİÖÇ]', '', filename)
        else:
            filename = re.sub(r'[^\w\s\-]', '', filename)

        # Replace spaces and multiple dashes with single underscore
        filename = re.sub(r'[\s\-]+', '_', filename)

        # Limit length
        return filename[:100]

    def format_duration(self, duration_seconds: float) -> str:
        """Format duration in seconds to human-readable string"""
        minutes = int(duration_seconds // 60)
        seconds = int(duration_seconds % 60)

        if minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def format_date(self, timestamp: str) -> str:
        """Format ISO timestamp to readable date"""
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return dt.strftime("%B %d, %Y at %I:%M %p")
        except Exception as e:
            logger.warning(f"⚠️ Error formatting date: {e}")
            return timestamp

    def get_language_display(self, language_code: str) -> str:
        """Get display name for language code"""
        language_map = {
            'tr': 'Turkish',
            'en': 'English',
            'de': 'German',
            'es': 'Spanish',
            'fr': 'French',
            'it': 'Italian',
            'pt': 'Portuguese',
            'ru': 'Russian',
            'ar': 'Arabic',
            'zh': 'Chinese',
            'ja': 'Japanese',
            'ko': 'Korean'
        }
        return language_map.get(language_code, language_code.upper())

    def prepare_recording_data(self, recording_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare recording data for template rendering.
        Adds formatted fields and helpers.
        """
        # Detect language
        language = self.detect_language(recording_data)

        # Get transcript from top-level (new structure) or summary.fullTranscript (old structure)
        full_transcript = recording_data.get('transcript', [])
        summary = recording_data.get('summary', {})

        # Fallback to summary.fullTranscript if transcript is empty
        if not full_transcript and isinstance(summary, dict):
            full_transcript = summary.get('fullTranscript', [])

        # Count speakers from transcript
        speakers_count = 1
        if full_transcript:
            unique_speakers = set()
            for entry in full_transcript:
                speaker = entry.get('speaker', 'Speaker 1')
                unique_speakers.add(speaker)
            speakers_count = len(unique_speakers)

        # Get key takeaways - prefer top-level keyPoints, fallback to summary.keyTakeaways
        key_takeaways = recording_data.get('keyPoints', [])
        if not key_takeaways and isinstance(summary, dict):
            key_takeaways = summary.get('keyTakeaways', [])

        # Get action items - prefer top-level actionItems, fallback to summary.actionItems
        action_items = recording_data.get('actionItems', [])
        if not action_items and isinstance(summary, dict):
            action_items = summary.get('actionItems', [])

        # Get summary text - handle both dict and string formats
        brief_summary = ''
        detailed_summary = ''
        if isinstance(summary, dict):
            brief_summary = summary.get('brief', '')
            detailed_summary = summary.get('detailed', '')
        elif isinstance(summary, str):
            detailed_summary = summary

        # Prepare enhanced data
        enhanced_data = {
            'id': recording_data.get('recordingId', recording_data.get('id', '')),
            'title': recording_data.get('title', 'Untitled Meeting'),
            'created_at': recording_data.get('createdAt', ''),
            'created_at_formatted': self.format_date(recording_data.get('createdAt', '')),
            'duration': recording_data.get('duration', 0),
            'duration_formatted': self.format_duration(recording_data.get('duration', 0)),
            'detected_language': language,
            'detected_language_display': self.get_language_display(language),
            'summary': {
                'brief': brief_summary,
                'detailed': detailed_summary,
                'key_takeaways': key_takeaways,
                'action_items': action_items,
                'full_transcript': full_transcript,
                'speakers_count': speakers_count
            },
            # Add top-level fields for templates
            'topics': recording_data.get('topics', []),
            'questions': recording_data.get('questions', []),
            'decisions': recording_data.get('decisions', []),
            'nextSteps': recording_data.get('nextSteps', []),
            'sentiment': recording_data.get('sentiment', 'neutral')
        }

        return enhanced_data

    def get_pdf_storage_path(self, recording_id: str) -> str:
        """Get the file path for a recording's PDF"""
        return os.path.join(self.pdf_storage_dir, f"{recording_id}.pdf")

    def get_stored_pdf(self, recording_id: str) -> Optional[bytes]:
        """Retrieve stored PDF if it exists"""
        pdf_path = self.get_pdf_storage_path(recording_id)

        if os.path.exists(pdf_path):
            try:
                with open(pdf_path, 'rb') as f:
                    logger.info(f"✅ Retrieved PDF from storage: {recording_id[:8]}...")
                    return f.read()
            except Exception as e:
                logger.warning(f"⚠️ Error reading stored PDF: {e}")
                return None

        return None

    def save_pdf(self, recording_id: str, pdf_data: bytes) -> tuple[bool, Optional[str]]:
        """
        Save generated PDF to storage.

        Returns:
            Tuple of (success: bool, file_path: Optional[str])
        """
        pdf_path = self.get_pdf_storage_path(recording_id)

        try:
            with open(pdf_path, 'wb') as f:
                f.write(pdf_data)
            logger.info(f"✅ Saved PDF to storage: {pdf_path}")
            return True, pdf_path
        except Exception as e:
            logger.error(f"❌ Error saving PDF: {e}")
            return False, None

    def delete_pdf(self, recording_id: str) -> bool:
        """Delete a stored PDF"""
        pdf_path = self.get_pdf_storage_path(recording_id)

        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
                logger.info(f"✅ Deleted PDF: {pdf_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Error deleting PDF: {e}")
            return False

    def generate_pdf(self, recording_data: Dict[str, Any], save_to_storage: bool = True) -> tuple[Optional[bytes], Optional[str], Optional[str]]:
        """
        Generate PDF report from recording data.

        Args:
            recording_data: Dictionary containing recording and analysis data
            save_to_storage: If True, save PDF to storage directory

        Returns:
            Tuple of (pdf_bytes, filename, error_message)
            - pdf_bytes: PDF file as bytes, or None if error
            - filename: Suggested filename for download
            - error_message: Error description if failed, None if successful
        """
        try:
            recording_id = recording_data.get('recordingId', '')
            logger.info(f"📄 Starting PDF generation for recording: {recording_id}")

            # Check if already exists in storage
            if save_to_storage:
                stored_pdf = self.get_stored_pdf(recording_id)
                if stored_pdf:
                    logger.info(f"✅ PDF already exists in storage for {recording_id}")
                    # Prepare filename
                    enhanced_data = self.prepare_recording_data(recording_data)
                    language = enhanced_data['detected_language']
                    title = enhanced_data['title']
                    sanitized_title = self.sanitize_filename(title, language)
                    date_str = datetime.now().strftime("%Y%m%d")
                    filename = f"{sanitized_title}_{date_str}.pdf"
                    return stored_pdf, filename, None

            # Prepare data for template
            enhanced_data = self.prepare_recording_data(recording_data)
            language = enhanced_data['detected_language']

            # Calculate total pages estimate
            total_pages = 2  # Cover + Summary
            if enhanced_data['summary']['key_takeaways']:
                total_pages += 1
            if enhanced_data['summary']['action_items']:
                total_pages += 1
            if enhanced_data['summary']['full_transcript']:
                # Estimate 10 entries per page
                transcript_pages = len(enhanced_data['summary']['full_transcript']) // 10 + 1
                total_pages += transcript_pages
            total_pages += 1  # Footer page

            # Read CSS content
            with open(self.css_path, 'r', encoding='utf-8') as f:
                css_content = f.read()

            # Render HTML template with inline CSS
            template = self.jinja_env.get_template('pdf/meeting_report.html')
            html_content = template.render(
                recording=enhanced_data,
                language=language,
                title=enhanced_data['title'],
                css_content=css_content,
                generated_at=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
                total_pages=total_pages
            )

            logger.info("✅ HTML template rendered successfully")

            # Generate PDF with WeasyPrint
            html_doc = HTML(string=html_content)
            pdf_bytes = html_doc.write_pdf()

            logger.info(f"✅ PDF generated successfully, size: {len(pdf_bytes)} bytes")

            # Save to storage if requested
            if save_to_storage:
                success, pdf_path = self.save_pdf(recording_id, pdf_bytes)
                if not success:
                    logger.warning(f"⚠️ Failed to save PDF to storage, but generation succeeded")

            # Generate filename with language-aware sanitization
            sanitized_title = self.sanitize_filename(enhanced_data['title'], language)
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"{sanitized_title}_{date_str}.pdf"

            logger.info(f"✅ PDF generation complete: {filename}")

            return pdf_bytes, filename, None

        except Exception as e:
            error_msg = f"Failed to generate PDF: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return None, None, error_msg


# Global service instance
_pdf_service = None


def get_pdf_service() -> PDFGeneratorService:
    """Get or create the global PDF service instance"""
    global _pdf_service
    if _pdf_service is None:
        _pdf_service = PDFGeneratorService()
    return _pdf_service
