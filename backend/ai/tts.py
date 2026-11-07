"""
ai/tts.py — Text-to-speech adapter for approved action shift briefings.
"""

from __future__ import annotations

import nexus_client as nc
from nexus_client import NexusTTSResult


def generate_briefing_audio(briefing_text: str, language: str = "en") -> NexusTTSResult:
    """
    Synthesize approved actions into shift audio briefing.
    Delegates to nexus_client which handles token logging.
    """
    return nc.synthesise_briefing(briefing_text, language=language)

