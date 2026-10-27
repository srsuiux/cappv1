from types import SimpleNamespace

from src.services.runs import RunManager
from src.tui import commands


class _Console:
    def print(self, *a, **k):
        pass


def _session(ws):
    return SimpleNamespace(ws=ws, runs=RunManager(ws), web=None, console=_Console())


def test_web_command_shares_the_sessions_runs_and_stops(ws, monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda url: True)
    s = _session(ws)
    commands.cmd_web(s, "")
    assert s.web and s.web.runs is s.runs and s.web.running
    commands.cmd_web(s, "stop")
    assert s.web is None


def test_init_offers_browser_or_terminal(ws, monkeypatch):
    opened = []
    monkeypatch.setattr(commands, "cmd_web", lambda session, args: opened.append(1))
    monkeypatch.setattr(commands, "select", lambda *a, **k: 0)
    commands._where_next(_session(ws))
    assert opened
    monkeypatch.setattr(commands, "select", lambda *a, **k: 1)
    commands._where_next(_session(ws))
    assert len(opened) == 1  # staying in the terminal opens nothing
