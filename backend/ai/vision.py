"""
ai/vision.py — Vision extraction adapter for handwritten sheets and equipment nameplates.
"""

from __future__ import annotations

import nexus_client as nc
from nexus_client import NexusVisionResult


def process_inspection_sheet(image_bytes: bytes, task_hint: str = "inspection_sheet") -> NexusVisionResult:
    """
    Extract fields and confidence scores from an image.
    Delegates to nexus_client which handles caching and token logging.
    """
    return nc.extract_sheet_vision(image_bytes, task_hint=task_hint)

