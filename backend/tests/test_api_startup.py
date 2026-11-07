"""
tests/test_api_startup.py — Test FastAPI app initialization and route registration.
Guarantees that main.py and all API route modules import and mount cleanly.
"""

import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import main


def test_fastapi_app_initialization():
    """Verify that the FastAPI application initializes with all required routers."""
    app = main.app
    assert app is not None
    assert app.title == "ResourceLens API"

    # Verify that all required route prefixes are mounted in OpenAPI schema
    paths = list(app.openapi()["paths"].keys())
    assert any("/api/upload" in p for p in paths), "Upload routes missing"
    assert any("/api/analysis" in p for p in paths), "Analysis routes missing"
    assert any("/api/review" in p for p in paths), "Review routes missing"
    assert any("/api/verify" in p for p in paths), "Verify routes missing"
    assert "/health" in paths, "Health check route missing"
