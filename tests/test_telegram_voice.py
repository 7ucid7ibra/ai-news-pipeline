from __future__ import annotations

from datetime import date

from src.distribute import telegram_voice as tv
from src.models import NewsItem, RankedItem, Source


def _make_ranked_item(idx: int, description_words: int = 20) -> RankedItem:
    description = " ".join(f"detail{n}" for n in range(description_words))
    item = NewsItem(
        title=f"owner{idx}/repo{idx}: Useful AI tool update number {idx}",
        url=f"https://github.com/owner{idx}/repo{idx}",
        source=Source.GITHUB,
        description=description,
        tags=["agent", "workflow", "open-source"],
    )
    return RankedItem(
        item=item,
        novelty=8,
        practicality=8,
        impact=8,
        testability=8,
        reasoning="This can improve practical developer workflows by reducing repetitive setup and context switching.",
    )


def test_impact_first_script_has_structure_and_no_scores(monkeypatch):
    monkeypatch.setattr(tv, "_text_to_speech", lambda text, tone: b"audio")
    ranked = [_make_ranked_item(i) for i in range(1, 4)]

    audio, transcript = tv.generate_voice_memo(
        ranked=ranked,
        test_results=[],
        voice_tone="conversational",
        top_n=3,
        narration_style="impact_first",
        target_minutes=6,
        include_scores=False,
    )

    assert audio == b"audio"
    assert "Ranking score:" not in transcript
    assert "out of 40" not in transcript
    assert transcript.count("Why it matters:") >= 3
    assert transcript.count("Practical use case:") >= 3


def test_script_includes_scores_when_enabled(monkeypatch):
    monkeypatch.setattr(tv, "_text_to_speech", lambda text, tone: b"audio")
    ranked = [_make_ranked_item(1)]

    _, transcript = tv.generate_voice_memo(
        ranked=ranked,
        test_results=[],
        voice_tone="conversational",
        top_n=1,
        narration_style="impact_first",
        target_minutes=6,
        include_scores=True,
    )

    assert "Ranking score:" in transcript


def test_duration_trimming_respects_target_window():
    ranked = [_make_ranked_item(i, description_words=80) for i in range(1, 25)]
    transcript = tv._build_voice_script(
        ranked=ranked,
        test_results=None,
        voice_tone="conversational",
        top_n=20,
        narration_style="impact_first",
        target_minutes=2,
        include_scores=False,
    )

    max_words = (2 + 1) * tv.WORDS_PER_MINUTE
    assert len(transcript.split()) <= max_words
    # Dynamic selection should reduce stories when text would exceed duration.
    assert transcript.count("Practical use case:") < 20


def test_audio_caption_is_bounded_for_telegram():
    caption = tv._build_audio_caption("x " * 5000, date(2026, 3, 7))
    assert len(caption) <= tv.TELEGRAM_AUDIO_CAPTION_LIMIT
