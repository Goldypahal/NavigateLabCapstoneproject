"""
ai/stt.py — Speech-to-text adapter for operator voice notes.
"""

from __future__ import annotations

import nexus_client as nc
from nexus_client import NexusSTTResult


def process_voice_note(audio_bytes: bytes, language: str = "en") -> NexusSTTResult:
    """
    Transcribe operator audio into timestamped segments.
    Delegates to nexus_client which handles caching and token logging.
    """
    return nc.transcribe_audio(audio_bytes, language=language)

