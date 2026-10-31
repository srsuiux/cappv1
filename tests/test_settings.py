import json
import stat

import pytest

from cappv1.services import settings
from cappv1.services.errors import ServiceError


def test_unconfigured_workspace_reports_so(ws):
    s = settings.read(ws)
    assert not s.configured and s.model == ""


def test_save_local_service_is_private_and_remembered(ws):
    s = settings.save(ws, "ollama", "gemma3:4b")
    assert s.configured and s.private and s.provider == "ollama" and s.model == "gemma3:4b"
    assert s.remembered["ollama"] == "gemma3:4b"


def test_online_service_needs_a_key(ws):
    with pytest.raises(ServiceError) as err:
        settings.save(ws, "openai", "gpt-4o-mini")
    assert err.value.code == "no_key"


def test_key_is_saved_but_never_returned(ws):
    s = settings.save(ws, "openai", "gpt-4o-mini", api_key="sk-secret-value-1234")
    assert s.keys_saved["openai"] and not s.private
    assert "sk-secret-value-1234" not in json.dumps(s.as_dict())
    assert stat.S_IMODE(ws.env_path.stat().st_mode) == 0o600  # owner-only: it holds a key


def test_switching_service_clears_the_old_fallback_model(ws):
    from cappv1.services import envfile

    envfile.set_values(ws, {"FALLBACK_MODEL": "old/model"})
    settings.save(ws, "ollama", "gemma3:4b")
    assert envfile.read(ws)["FALLBACK_MODEL"] == ""


def test_each_service_remembers_its_own_last_model(ws):
    settings.save(ws, "openai", "gpt-4o", api_key="k")
    settings.save(ws, "ollama", "gemma3:4b")
    s = settings.read(ws)
    assert s.remembered["openai"] == "gpt-4o" and s.remembered["ollama"] == "gemma3:4b"


def test_empty_model_is_refused(ws):
    with pytest.raises(ServiceError) as err:
        settings.save(ws, "ollama", "  ")
    assert err.value.code == "no_model"


def test_unknown_service_is_refused(ws):
    with pytest.raises(ServiceError):
        settings.save(ws, "nonsense", "x")
