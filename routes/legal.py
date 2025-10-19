from flask import Blueprint, send_file, abort, request, jsonify
import os
import logging
from pathlib import Path

legal_bp = Blueprint('legal', __name__)

# Supported locales
SUPPORTED_LOCALES = ['en', 'tr', 'de', 'fr', 'es', 'ar']
SUPPORTED_DOCUMENTS = ['privacy', 'terms']

def get_logger():
    return logging.getLogger('braindumpster.routes.legal')

def get_content_path():
    """Get the path to the content directory"""
    # Go up from braindumpster_python to project root, then to content
    current_dir = Path(__file__).parent.parent  # braindumpster_python
    project_root = current_dir.parent  # project root
    return project_root / "content"

@legal_bp.route('/<locale>/<document_type>')
def serve_legal_document(locale, document_type):
    """Serve legal documents in markdown format with proper headers"""
    logger = get_logger()

    # Validate inputs
    if locale not in SUPPORTED_LOCALES:
        logger.warning(f"Unsupported locale requested: {locale}")
        abort(404)

    if document_type not in SUPPORTED_DOCUMENTS:
        logger.warning(f"Unsupported document type requested: {document_type}")
        abort(404)

    # Construct file path
    content_path = get_content_path()
    file_path = content_path / locale / f"{document_type}.md"

    # Check if file exists
    if not file_path.exists():
        logger.error(f"Legal document not found: {file_path}")
        # Fallback to English if available
        fallback_path = content_path / "en" / f"{document_type}.md"
        if fallback_path.exists():
            logger.info(f"Falling back to English version: {fallback_path}")
            file_path = fallback_path
        else:
            abort(404)

    try:
        logger.info(f"Serving legal document: {file_path}")

        # Read and return markdown content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        response = jsonify({
            "locale": locale,
            "document_type": document_type,
            "content": content,
            "format": "markdown"
        })

        # Set caching headers
        response.headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour
        response.headers['Content-Language'] = locale

        return response

    except Exception as e:
        logger.error(f"Error serving legal document {file_path}: {e}")
        abort(500)

@legal_bp.route('/<locale>/<document_type>/html')
def serve_legal_document_html(locale, document_type):
    """Serve legal documents in HTML format"""
    logger = get_logger()

    # Validate inputs
    if locale not in SUPPORTED_LOCALES:
        abort(404)

    if document_type not in SUPPORTED_DOCUMENTS:
        abort(404)

    # Construct file path for HTML version
    content_path = get_content_path()
    file_path = content_path / locale / f"{document_type}.html"

    # Check if file exists
    if not file_path.exists():
        logger.warning(f"HTML version not found: {file_path}")
        # Fallback to English if available
        fallback_path = content_path / "en" / f"{document_type}.html"
        if fallback_path.exists():
            file_path = fallback_path
        else:
            # If no HTML, return markdown version
            return serve_legal_document(locale, document_type)

    try:
        logger.info(f"Serving HTML legal document: {file_path}")

        response = send_file(
            file_path,
            mimetype='text/html',
            as_attachment=False
        )

        # Set caching headers
        response.headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour
        response.headers['Content-Language'] = locale

        return response

    except Exception as e:
        logger.error(f"Error serving HTML legal document {file_path}: {e}")
        abort(500)

@legal_bp.route('/supported-locales')
def get_supported_locales():
    """Return list of supported locales for legal documents"""
    return jsonify({
        "supported_locales": SUPPORTED_LOCALES,
        "supported_documents": SUPPORTED_DOCUMENTS,
        "base_url": request.base_url.replace('/supported-locales', '')
    })

@legal_bp.route('/health')
def health_check():
    """Health check endpoint for legal document service"""
    logger = get_logger()

    content_path = get_content_path()
    status = {
        "status": "healthy",
        "content_path": str(content_path),
        "supported_locales": SUPPORTED_LOCALES,
        "available_documents": {}
    }

    # Check which documents are available
    for locale in SUPPORTED_LOCALES:
        status["available_documents"][locale] = {}
        for doc_type in SUPPORTED_DOCUMENTS:
            md_path = content_path / locale / f"{doc_type}.md"
            html_path = content_path / locale / f"{doc_type}.html"
            status["available_documents"][locale][doc_type] = {
                "markdown": md_path.exists(),
                "html": html_path.exists()
            }

    logger.info("Legal document service health check completed")
    return jsonify(status)