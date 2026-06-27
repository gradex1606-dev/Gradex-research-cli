"""Tests for security scrubbing and trace integration."""

from __future__ import annotations

from pathlib import Path

from gradex.security.scrubber import scrub, scrub_dict
from gradex.traces import TraceReader, TraceWriter


def test_scrub_anthropic_key() -> None:
    text = "Using key sk-ant-api03-abc123def456ghi789jkl012"
    result = scrub(text)
    assert "sk-ant" not in result
    assert "[REDACTED:anthropic-key]" in result


def test_scrub_openai_key() -> None:
    text = "key=sk-abcdefghijklmnopqrstuvwxyz1234"
    result = scrub(text)
    assert "sk-abc" not in result
    assert "[REDACTED" in result


def test_scrub_groq_key() -> None:
    text = "Authorization: gsk_abc123def456ghi789jklmno"
    result = scrub(text)
    assert "gsk_" not in result


def test_scrub_openrouter_key() -> None:
    text = "key=sk-or-v1-abcdefghijklmnopqrstuvwxyz123456"
    result = scrub(text)
    assert "sk-or-v1" not in result
    assert "[REDACTED:openrouter-key]" in result


def test_scrub_github_token() -> None:
    text = "token ghp_abcdefghijklmnopqrstuvwxyz123456789012"
    result = scrub(text)
    assert "ghp_" not in result


def test_scrub_aws_key() -> None:
    text = "aws_access_key_id=AKIAIOSFODNN7EXAMPLE"
    result = scrub(text)
    assert "AKIA" not in result


def test_scrub_bearer_token() -> None:
    text = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz1234567890"
    result = scrub(text)
    assert "Bearer abcdef" not in result
    assert "Bearer [REDACTED]" in result


def test_scrub_clean_text_unchanged() -> None:
    text = "Score: 41.2\nBenchmark complete"
    result = scrub(text)
    assert result == text


def test_scrub_dict_recursive() -> None:
    data = {
        "msg": "key is sk-abcdefghijklmnopqrstuvwx",
        "nested": {"token": "sk-zyxwvutsrqponmlkjihg"},
        "number": 42,
    }
    result = scrub_dict(data)
    assert "[REDACTED" in result["msg"]
    assert "[REDACTED" in result["nested"]["token"]
    assert result["number"] == 42


def test_scrub_dict_does_not_mutate_input() -> None:
    original = {"key": "sk-abcdefghijklmnopqrstuvwx12345"}
    scrub_dict(original)
    assert "sk-" in original["key"]


def test_traces_writer_scrubs_on_write(tmp_path: Path) -> None:
    trace_path = tmp_path / "test.jsonl"
    writer = TraceWriter(trace_path)
    writer.write("info", "API key is sk-abcdefghijklmnopqrstuvwxyz", {})
    reader = TraceReader(trace_path)
    entries = reader.read_all()
    assert "sk-abc" not in entries[0]["msg"]
    assert "[REDACTED" in entries[0]["msg"]
