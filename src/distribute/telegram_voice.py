"""Telegram voice memo distribution — sends daily digest as an audio memo."""

from __future__ import annotations

import io
import logging
import os
import requests
from datetime import date
from pathlib import Path

from src.models import RankedItem, TestResult

logger = logging.getLogger(__name__)

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"


def generate_voice_memo(
    ranked: list[RankedItem],
    test_results: list[TestResult] | None,
    voice_tone: str,
    top_n: int = 10,
) -> tuple[bytes, str]:
    """Generate an audio memo summarizing the top stories and tools.

    Args:
        ranked: Ranked items (top first)
        test_results: Results from tool testing (if any)
        voice_tone: Voice/tone style prompt (e.g., "casual tech bro", "professional")
        top_n: How many stories to include (default 10)

    Returns:
        Tuple of (audio_bytes, transcript_text)
    """
    # Build the script
    items_to_read = ranked[:top_n]

    script_lines = [
        "Hey! Here's your AI news digest for today.",
        "",
    ]

    # Add stories
    script_lines.append("**Top Stories:**")
    for i, item in enumerate(items_to_read, 1):
        sources = ", ".join(item.item.raw_data.get("all_sources", [item.item.source.value]))
        script_lines.append(f"{i}. {item.item.title} from {sources}. Score: {item.total_score} out of 40.")

    # Add tools if any passed testing
    if test_results:
        passed_tools = [r for r in test_results if r.verdict.value == "pass"]
        if passed_tools:
            script_lines.append("")
            script_lines.append("**New Tools Worth Checking Out:**")
            for tool in passed_tools[:3]:  # Top 3 tools
                script_lines.append(
                    f"- {tool.item.item.title}: {tool.evaluation}. "
                    f"Install with: {tool.install_command}"
                )

    script_lines.append("")
    script_lines.append("That's it for today. Stay curious!")

    script = "\n".join(script_lines)

    # Convert to speech
    audio_bytes = _text_to_speech(script, voice_tone)
    return audio_bytes, script


def send_telegram_memo(
    audio_bytes: bytes,
    transcript: str,
    bot_token: str,
    chat_ids: list[str],
    run_date: date | None = None,
) -> bool:
    """Send audio memo to Telegram.

    Args:
        audio_bytes: Audio file data
        transcript: Text transcript for context
        bot_token: Telegram bot token
        chat_ids: List of chat IDs to send to (can be user IDs or group IDs)
        run_date: Date for the memo (default today)

    Returns:
        True if successful
    """
    if not audio_bytes or not bot_token or not chat_ids:
        logger.warning("Missing audio, bot token, or chat IDs for Telegram")
        return False

    run_date = run_date or date.today()

    # Send to each chat
    success_count = 0
    for chat_id in chat_ids:
        try:
            # Send audio file
            url = f"https://api.telegram.org/bot{bot_token}/sendAudio"
            files = {"audio": ("ai_digest.mp3", io.BytesIO(audio_bytes))}
            data = {
                "chat_id": chat_id,
                "title": f"AI News Digest — {run_date}",
                "performer": "AI News Pipeline",
                "caption": f"📰 Daily AI News Digest\n\n{transcript[:1000]}...",
            }

            response = requests.post(url, files=files, data=data, timeout=30)
            if response.status_code == 200:
                logger.info(f"Sent voice memo to Telegram chat: {chat_id}")
                success_count += 1
            else:
                logger.error(f"Telegram API error: {response.status_code} — {response.text[:200]}")
        except Exception as e:
            logger.exception(f"Failed to send to Telegram chat {chat_id}: {e}")

    return success_count > 0


def _text_to_speech(text: str, voice_tone: str) -> bytes:
    """Convert text to speech using ElevenLabs API.

    Args:
        text: Script to convert
        voice_tone: Voice style description (passed in system message)

    Returns:
        Audio bytes (MP3)
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")

    if not api_key or not voice_id:
        logger.error("ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID not set")
        raise ValueError("Missing ElevenLabs credentials")

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    try:
        response = requests.post(
            f"{ELEVENLABS_API_URL}/{voice_id}",
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.content

    except requests.exceptions.RequestException as e:
        logger.error(f"ElevenLabs API error: {e}")
        raise


def save_transcript(transcript: str, run_date: date | None = None) -> Path:
    """Save the transcript alongside the audio memo.

    Args:
        transcript: Text transcript
        run_date: Date for the memo

    Returns:
        Path where transcript was saved
    """
    from src.config import PROJECT_ROOT

    run_date = run_date or date.today()
    output_dir = PROJECT_ROOT / "output" / "voice_memos"
    output_dir.mkdir(parents=True, exist_ok=True)

    transcript_file = output_dir / f"{run_date}_transcript.txt"
    transcript_file.write_text(transcript)

    return transcript_file
