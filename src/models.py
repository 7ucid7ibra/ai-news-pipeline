"""Data models for the AI News Automation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Source(str, Enum):
    HACKERNEWS = "hackernews"
    REDDIT = "reddit"
    GITHUB = "github"
    PRODUCTHUNT = "producthunt"
    RSS = "rss"
    TWITTER = "twitter"
    YOUTUBE = "youtube"


@dataclass
class NewsItem:
    """A single piece of AI news/tool from any source."""

    title: str
    url: str
    source: Source
    description: str
    score: int = 0  # raw score (upvotes/stars/likes)
    timestamp: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)

    # Set by aggregator
    normalized_score: float = 0.0  # 0-100
    cross_posted: int = 1  # how many sources mention this

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source.value,
            "description": self.description,
            "score": self.score,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
            "normalized_score": self.normalized_score,
            "cross_posted": self.cross_posted,
        }


@dataclass
class RankedItem:
    """A NewsItem after LLM ranking."""

    item: NewsItem
    novelty: int = 0  # 0-10
    practicality: int = 0  # 0-10
    impact: int = 0  # 0-10
    testability: int = 0  # 0-10
    reasoning: str = ""

    @property
    def total_score(self) -> int:
        return self.novelty + self.practicality + self.impact + self.testability

    def to_dict(self) -> dict:
        return {
            **self.item.to_dict(),
            "ranking": {
                "novelty": self.novelty,
                "practicality": self.practicality,
                "impact": self.impact,
                "testability": self.testability,
                "total": self.total_score,
                "reasoning": self.reasoning,
            },
        }


class TestVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"  # couldn't test (needs hardware, paid API, etc.)


@dataclass
class TestResult:
    """Result of a Claude agent testing a tool."""

    item: RankedItem
    verdict: TestVerdict
    install_method: str = ""  # pip, npm, brew, mcp, etc.
    install_command: str = ""
    test_log: str = ""
    evaluation: str = ""
    security_concerns: list[str] = field(default_factory=list)
    recommended_config: dict = field(default_factory=dict)  # MCP/skill config if applicable

    def to_dict(self) -> dict:
        return {
            **self.item.to_dict(),
            "test": {
                "verdict": self.verdict.value,
                "install_method": self.install_method,
                "install_command": self.install_command,
                "evaluation": self.evaluation,
                "security_concerns": self.security_concerns,
            },
        }
