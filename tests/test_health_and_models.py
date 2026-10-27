from src.services import health, models, settings
from src.services.errors import ServiceError
import pytest


def test_doctor_passes_for_a_working_local_setup(configured):
    results = health.run_all(configured)
    failed = [c for c in results if not c.ok]
    assert not failed, failed


def test_doctor_explains_how_to_fix_a_stopped_ollama(ws):
    from src.services import envfile

    envfile.set_values(ws, {"OLLAMA_BASE_URL": "http://127.0.0.1:9"})  # nothing listens here
    settings.save(ws, "ollama", "gemma3:4b")
    bad = {c.label: c for c in health.run_all(ws)}["Ollama is running"]
    assert not bad.ok and "Ollama" in bad.detail


def test_doctor_flags_a_missing_key(ws):
    from src.services import envfile

    envfile.set_values(ws, {"PROVIDER": "openai"})
    checks = {c.label: c for c in health.run_all(ws, live=False)}
    assert not checks["OPENAI_API_KEY is set"].ok


def test_only_models_that_can_read_images_are_offered(configured):
    assert [m.id for m in models.ollama_vision(configured)] == ["gemma3:4b"]


def test_ollama_down_is_a_friendly_error(ws):
    from src.services import envfile

    envfile.set_values(ws, {"OLLAMA_BASE_URL": "http://127.0.0.1:9"})
    with pytest.raises(ServiceError) as err:
        models.ollama_vision(ws)
    assert err.value.code == "ollama_down"


def test_openrouter_catalog_groups_by_maker_cheapest_first(monkeypatch):
    fake = [
        {"id": "a/free-one:free", "name": "x", "free": True, "price": 0.0},
        {"id": "a/pricey", "name": "x", "free": False, "price": 5.0},
        {"id": "a/cheap", "name": "x", "free": False, "price": 0.1},
        {"id": "b/mid", "name": "x", "free": False, "price": 1.0},
    ]
    monkeypatch.setattr("src.models.fetch_openrouter_vision_models", lambda: fake)
    cat = models.openrouter_catalog()
    assert [m.id for m in cat.free] == ["a/free-one:free"]
    assert [m.id for m in cat.cheapest(2)] == ["a/cheap", "b/mid"]
    assert list(cat.makers()) == ["a", "b"] and [m.id for m in cat.makers()["a"]] == ["a/cheap", "a/pricey"]
