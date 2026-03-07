from __future__ import annotations

import sys
import types
from datetime import date
from pathlib import Path

# run_pipeline imports src.pipeline.aggregator -> rapidfuzz.
# Stub it for test environments where rapidfuzz is not installed.
if "rapidfuzz" not in sys.modules:
    fake_fuzz = types.SimpleNamespace(token_sort_ratio=lambda _a, _b: 0)
    sys.modules["rapidfuzz"] = types.SimpleNamespace(fuzz=fake_fuzz)

import run_pipeline
from src.models import NewsItem, RankedItem, Source


def _sample_ranked() -> list[RankedItem]:
    item = NewsItem(
        title="owner/repo: Example tool",
        url="https://github.com/owner/repo",
        source=Source.GITHUB,
        description="Example description",
        tags=["agent"],
    )
    return [RankedItem(item=item, novelty=8, practicality=8, impact=8, testability=8)]


def _base_config() -> dict:
    return {
        "distribution": {
            "telegram_enabled": True,
            "telegram_chat_ids": ["5100045652"],
            "telegram_voice_tone": "conversational",
            "telegram_top_n": 5,
            "telegram_narration_style": "impact_first",
            "telegram_target_minutes": 6,
            "telegram_include_scores": False,
            "obsidian_vault": "",
            "github_repo": "",
        }
    }


def _patch_non_telegram_side_effects(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_pipeline, "generate_digest", lambda *args, **kwargs: "digest")
    monkeypatch.setattr(run_pipeline, "save_digest", lambda *args, **kwargs: tmp_path / "digest.md")
    monkeypatch.setattr(run_pipeline, "install_approved_tools", lambda *args, **kwargs: {"mcp_servers": 0, "skills": 0})
    monkeypatch.setattr(run_pipeline, "save_to_obsidian", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_pipeline, "publish_to_github", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_pipeline, "save_transcript", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_pipeline, "_build_telegram_text_fallback", lambda *args, **kwargs: "text summary")


def test_distribute_sends_voice_and_text(monkeypatch, tmp_path):
    _patch_non_telegram_side_effects(monkeypatch, tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")

    calls = {"voice": 0, "text": 0}

    def fake_generate_voice(*args, **kwargs):
        assert kwargs["narration_style"] == "impact_first"
        assert kwargs["target_minutes"] == 6
        assert kwargs["include_scores"] is False
        return b"audio", "transcript"

    def fake_send_voice(*args, **kwargs):
        calls["voice"] += 1
        return True

    def fake_send_text(*args, **kwargs):
        calls["text"] += 1
        return True

    monkeypatch.setattr(run_pipeline, "generate_voice_memo", fake_generate_voice)
    monkeypatch.setattr(run_pipeline, "send_telegram_memo", fake_send_voice)
    monkeypatch.setattr(run_pipeline, "send_telegram_text", fake_send_text)

    run_pipeline.distribute(
        ranked=_sample_ranked(),
        test_results=[],
        config=_base_config(),
        run_date=date(2026, 3, 7),
    )

    assert calls["voice"] == 1
    assert calls["text"] == 1


def test_distribute_sends_text_when_voice_generation_fails(monkeypatch, tmp_path):
    _patch_non_telegram_side_effects(monkeypatch, tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")

    calls = {"voice": 0, "text": 0}

    def fake_generate_voice(*args, **kwargs):
        raise RuntimeError("tts failed")

    def fake_send_voice(*args, **kwargs):
        calls["voice"] += 1
        return True

    def fake_send_text(*args, **kwargs):
        calls["text"] += 1
        return True

    monkeypatch.setattr(run_pipeline, "generate_voice_memo", fake_generate_voice)
    monkeypatch.setattr(run_pipeline, "send_telegram_memo", fake_send_voice)
    monkeypatch.setattr(run_pipeline, "send_telegram_text", fake_send_text)

    run_pipeline.distribute(
        ranked=_sample_ranked(),
        test_results=[],
        config=_base_config(),
        run_date=date(2026, 3, 7),
    )

    assert calls["voice"] == 0
    assert calls["text"] == 1
