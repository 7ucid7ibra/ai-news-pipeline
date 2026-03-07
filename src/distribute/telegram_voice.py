"""Telegram voice memo distribution — sends daily digest as an audio memo."""

from __future__ import annotations

import io
import logging
import os
import re
import requests
from datetime import date
from pathlib import Path

from src.models import RankedItem, TestResult

logger = logging.getLogger(__name__)

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
TELEGRAM_AUDIO_CAPTION_LIMIT = 1024
DEFAULT_ELEVENLABS_MODELS = [
    "eleven_flash_v2_5",
    "eleven_turbo_v2_5",
    "eleven_multilingual_v2",
]
WORDS_PER_MINUTE = 145


def generate_voice_memo(
    ranked: list[RankedItem],
    test_results: list[TestResult] | None,
    voice_tone: str,
    top_n: int = 10,
    narration_style: str = "impact_first",
    target_minutes: int = 6,
    include_scores: bool = False,
) -> tuple[bytes, str]:
    """Generate an audio memo summarizing the top stories and tools.

    Args:
        ranked: Ranked items (top first)
        test_results: Results from tool testing (if any)
        voice_tone: Voice/tone style prompt (e.g., "casual tech bro", "professional")
        top_n: How many stories to include (default 10)
        narration_style: Narrative style for spoken script.
        target_minutes: Desired audio length target.
        include_scores: Whether to mention ranking scores in narration.

    Returns:
        Tuple of (audio_bytes, transcript_text)
    """
    script = _build_voice_script(
        ranked=ranked,
        test_results=test_results,
        voice_tone=voice_tone,
        top_n=top_n,
        narration_style=narration_style,
        target_minutes=target_minutes,
        include_scores=include_scores,
    )

    # Convert to speech
    audio_bytes = _text_to_speech(script, voice_tone)
    return audio_bytes, script


def _build_voice_script(
    ranked: list[RankedItem],
    test_results: list[TestResult] | None,
    voice_tone: str,
    top_n: int,
    narration_style: str,
    target_minutes: int,
    include_scores: bool,
) -> str:
    """Build a conversational voice script with duration-aware trimming."""
    style = (narration_style or "impact_first").strip().lower()
    clamped_top_n = max(1, top_n)
    clamped_target = max(2, min(12, int(target_minutes)))
    max_words = (clamped_target + 1) * WORDS_PER_MINUTE

    intro = [
        f"Hey, here's your AI news briefing for {date.today()}.",
        "I picked the stories most likely to change what you can build right now.",
    ]
    if voice_tone:
        intro.append(f"I'll keep this {voice_tone}.")

    lines = intro + [""]

    if test_results is not None:
        passed = sum(1 for r in test_results if r.verdict.value == "pass")
        skipped = sum(1 for r in test_results if r.verdict.value == "skip")
        failed = sum(1 for r in test_results if r.verdict.value == "fail")
        lines.append(
            f"Quick testing update: {len(test_results)} tools checked, "
            f"{passed} passed, {failed} failed, and {skipped} skipped."
        )
        lines.append("")

    selected = 0
    for idx, item in enumerate(ranked[:clamped_top_n], 1):
        block = _build_story_block(
            item=item,
            index=idx,
            narration_style=style,
            include_scores=include_scores,
        )
        proposed = lines + block + [""]
        if _estimate_words(proposed) > max_words and selected > 0:
            break
        lines = proposed
        selected += 1

    if selected == 0 and ranked:
        lines.extend(
            _build_story_block(
                item=ranked[0],
                index=1,
                narration_style=style,
                include_scores=include_scores,
            )
        )
        lines.append("")

    lines.append(
        "That's your briefing. If you want, I can also break down one of these stories into an implementation plan."
    )
    return "\n".join(lines).strip()


def _build_story_block(
    item: RankedItem,
    index: int,
    narration_style: str,
    include_scores: bool,
) -> list[str]:
    """Build one conversational story block: what happened, impact, and use case."""
    transitions = [
        "First up",
        "Next",
        "Also worth your attention",
        "Another one to watch",
        "And this one matters",
    ]
    lead = transitions[(index - 1) % len(transitions)]

    title = _sanitize_title(item.item.title)
    description = _sanitize_sentence(item.item.description, max_words=28)
    reasoning = _sanitize_sentence(item.reasoning, max_words=24)
    source = _format_sources(item)
    tags = item.item.tags[:8]

    if description:
        what_happened = f"{lead}: {title}. In short, {description}"
    else:
        what_happened = f"{lead}: {title}. This came up from {source}."

    impact_basis = reasoning or description
    if impact_basis:
        why_it_matters = f"Why it matters: {impact_basis}"
    else:
        why_it_matters = (
            "Why it matters: this signals a shift in available AI capabilities that can change day-to-day workflows."
        )

    practical_use_case = _infer_use_case(item, tags)
    use_case = f"Practical use case: {practical_use_case}"

    block = [what_happened, why_it_matters, use_case]
    if include_scores:
        block.append(f"Ranking score: {item.total_score} out of 40.")
    return block


def _sanitize_title(raw: str) -> str:
    """Clean noisy titles for speech output."""
    title = (raw or "").strip()
    title = re.sub(r"^\[[^\]]+\]\s*", "", title)
    title = re.sub(r"\s+", " ", title)

    if ":" in title:
        left, right = title.split(":", 1)
        if "/" in left and right.strip():
            title = right.strip()

    title = title.replace("—", "-").replace("–", "-")
    return _sanitize_sentence(title, max_words=22)


def _sanitize_sentence(text: str, max_words: int = 24) -> str:
    """Normalize spacing/markdown and trim to a manageable spoken length."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text.replace("**", " ").strip())
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        return ""

    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]).rstrip(" ,;:.") + "..."
    if not cleaned.endswith((".", "!", "?")):
        cleaned += "."
    return cleaned


def _format_sources(item: RankedItem) -> str:
    sources = item.item.raw_data.get("all_sources", [item.item.source.value])
    if isinstance(sources, list):
        return ", ".join(str(s) for s in sources[:3])
    return str(sources)


def _infer_use_case(item: RankedItem, tags: list[str]) -> str:
    """Infer one concrete use case from title/url/tags without extra LLM calls."""
    title = item.item.title.lower()
    url = item.item.url.lower()
    haystack = " ".join([title, item.item.description.lower(), " ".join(t.lower() for t in tags)])

    if "github.com" in url:
        return (
            "Clone the repo in a sandbox, run the quickstart, and test whether it can replace one repetitive part "
            "of your weekly workflow."
        )
    if any(k in haystack for k in ["agent", "mcp", "workflow", "automation"]):
        return (
            "Use it to automate one multi-step task, like triaging issues, summarizing docs, or drafting code changes."
        )
    if any(k in haystack for k in ["voice", "speech", "audio", "transcription"]):
        return (
            "Prototype a voice feature in an existing app and validate latency and quality with real user prompts."
        )
    if any(k in haystack for k in ["model", "llm", "gpt", "claude", "gemini"]):
        return (
            "Benchmark it on one real prompt set from your work and compare quality, cost, and speed with your current model."
        )
    return (
        "Try a focused one-hour pilot with one teammate to see if it saves time or improves output quality on a real task."
    )


def _estimate_words(lines: list[str]) -> int:
    return len(" ".join(lines).split())


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
            caption = _build_audio_caption(transcript, run_date)
            data = {
                "chat_id": chat_id,
                "title": f"AI News Digest — {run_date}",
                "performer": "AI News Pipeline",
                "caption": caption,
            }

            response = requests.post(
                url,
                files={"audio": ("ai_digest.mp3", io.BytesIO(audio_bytes))},
                data=data,
                timeout=30,
            )
            if response.status_code == 200:
                logger.info(f"Sent voice memo to Telegram chat: {chat_id}")
                success_count += 1
            else:
                # Defensive retry with minimal caption if Telegram still rejects caption length.
                if response.status_code == 400 and "caption is too long" in response.text.lower():
                    retry_data = {
                        "chat_id": chat_id,
                        "title": f"AI News Digest — {run_date}",
                        "performer": "AI News Pipeline",
                        "caption": f"AI News Digest — {run_date}",
                    }
                    retry_response = requests.post(
                        url,
                        files={"audio": ("ai_digest.mp3", io.BytesIO(audio_bytes))},
                        data=retry_data,
                        timeout=30,
                    )
                    if retry_response.status_code == 200:
                        logger.info(f"Sent voice memo to Telegram chat after caption retry: {chat_id}")
                        success_count += 1
                        continue
                    logger.error(
                        f"Telegram API retry error: {retry_response.status_code} — "
                        f"{retry_response.text[:200]}"
                    )
                logger.error(f"Telegram API error: {response.status_code} — {response.text[:200]}")
        except Exception as e:
            logger.exception(f"Failed to send to Telegram chat {chat_id}: {e}")

    return success_count > 0


def send_telegram_text(
    text: str,
    bot_token: str,
    chat_ids: list[str],
    run_date: date | None = None,
) -> bool:
    """Send a plain text digest message to Telegram chats."""
    if not text or not bot_token or not chat_ids:
        logger.warning("Missing text, bot token, or chat IDs for Telegram")
        return False

    run_date = run_date or date.today()
    max_len = 4000  # Telegram message limit is 4096 chars
    message = text[:max_len]

    success_count = 0
    for chat_id in chat_ids:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": True,
            }
            response = requests.post(url, data=data, timeout=20)
            if response.status_code == 200:
                logger.info(f"Sent text digest to Telegram chat: {chat_id} ({run_date})")
                success_count += 1
            else:
                logger.error(f"Telegram API text error: {response.status_code} — {response.text[:200]}")
        except Exception as e:
            logger.exception(f"Failed to send text digest to Telegram chat {chat_id}: {e}")

    return success_count > 0


def _build_audio_caption(transcript: str, run_date: date) -> str:
    """Build a Telegram-safe audio caption within Telegram's caption limit."""
    header = f"AI News Digest — {run_date}\n\n"
    body = transcript.replace("**", "").strip()

    available = TELEGRAM_AUDIO_CAPTION_LIMIT - len(header)
    if available <= 0:
        return header[:TELEGRAM_AUDIO_CAPTION_LIMIT]

    if len(body) > available:
        if available > 1:
            body = body[: available - 1].rstrip() + "…"
        else:
            body = ""

    return header + body


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

    configured_model = os.environ.get("ELEVENLABS_MODEL_ID", "").strip()
    models_to_try = [configured_model] if configured_model else []
    for model in DEFAULT_ELEVENLABS_MODELS:
        if model not in models_to_try:
            models_to_try.append(model)

    last_exception: Exception | None = None
    for model_id in models_to_try:
        payload = {
            "text": text,
            "model_id": model_id,
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
            logger.info(f"ElevenLabs TTS succeeded with model: {model_id}")
            return response.content
        except requests.exceptions.RequestException as e:
            last_exception = e
            logger.warning(f"ElevenLabs TTS failed with model {model_id}: {e}")

    logger.error("ElevenLabs API error: all configured models failed")
    if last_exception:
        raise last_exception
    raise RuntimeError("ElevenLabs TTS failed: no model attempts were made")


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
