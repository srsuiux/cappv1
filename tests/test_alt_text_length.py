"""The alt text length setting reaches the prompt, the token limit and the API."""

import pytest

from cappv1 import config as config_mod
from cappv1.llm_client import _build_text_messages, _rule
from cappv1.llm_prompts import _TABLE_SYSTEM_PROMPT
from cappv1.llm_providers import _build_request
from cappv1.pptx_reader import SlideContext


def _config(monkeypatch, tmp_path, **env):
    for key in ("ALT_TEXT_LENGTH", "MAX_ALT_TEXT_CHARS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PROVIDER", "ollama")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return config_mod.load_config(tmp_path)


@pytest.mark.parametrize("length,chars", [("short", 80), ("standard", 125), ("long", 400)])
def test_each_length_sets_the_limit(monkeypatch, tmp_path, length, chars):
    cfg = _config(monkeypatch, tmp_path, ALT_TEXT_LENGTH=length)
    assert cfg.alt_text_length == length and cfg.max_alt_text_chars == chars


def test_default_is_standard(monkeypatch, tmp_path):
    assert _config(monkeypatch, tmp_path).max_alt_text_chars == 125


def test_an_exact_limit_wins_over_the_length(monkeypatch, tmp_path):
    assert _config(monkeypatch, tmp_path, ALT_TEXT_LENGTH="short", MAX_ALT_TEXT_CHARS="200").max_alt_text_chars == 200


def test_a_bad_length_says_what_is_allowed(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match="short, standard, long"):
        _config(monkeypatch, tmp_path, ALT_TEXT_LENGTH="huge")


def test_the_prompt_asks_for_the_chosen_length(monkeypatch, tmp_path):
    ctx = SlideContext(index=0, section=None, title="", body_text="", notes="")
    texts = {}
    for length in ("short", "standard", "long"):
        cfg = _config(monkeypatch, tmp_path, ALT_TEXT_LENGTH=length)
        system = _build_text_messages(_TABLE_SYSTEM_PROMPT, "a | b", ctx, _rule(cfg), "Table")[0]["content"]
        assert "{" not in system
        texts[length] = system
    assert "very brief" in texts["short"] and "under 80" in texts["short"]
    assert "Be concise" in texts["standard"] and "under 125" in texts["standard"]
    assert "detailed" in texts["long"] and "400" in texts["long"]


def test_long_descriptions_get_room_in_the_reply(monkeypatch, tmp_path):
    short = _build_request(_config(monkeypatch, tmp_path, ALT_TEXT_LENGTH="short"), "m", [])[2]
    long = _build_request(_config(monkeypatch, tmp_path, ALT_TEXT_LENGTH="long"), "m", [])[2]
    assert short["max_tokens"] == 200 and long["max_tokens"] == 400
