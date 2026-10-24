"""Restarting or stopping the daemon from the apps (daemon/shutdown.py): what each service manager's daemon
does when stopped (daemon/managers.py), and how the process ends (daemon/server.py::end)."""

import asyncio
import os
import signal
import sys
from dataclasses import replace

import pytest

from assistant.daemon import launchd, managers, server, systemd
from assistant.daemon.shutdown import Ending, Pending, Shutdown
from assistant.protocol import NoEndingError, StartupStatus, StopRefusedError


class _Runs:
    def __init__(self, running: int = 0) -> None:
        self.running = running
        self.ended = asyncio.Event()
        if not running:
            self.ended.set()

    def runs_in_progress(self) -> int:
        return self.running

    async def until_no_runs(self) -> None:
        await self.ended.wait()

    def cancel_runs(self) -> int:
        cancelled, self.running = self.running, 0
        self.ended.set()
        return cancelled


class _Manager:
    def __init__(self, refusal: str | None = None, fails: bool = False) -> None:
        self.refusal = refusal
        self.fails = fails
        self.stops = 0

    def stop_refusal(self) -> str | None:
        return self.refusal

    async def stop(self, stop: asyncio.Event) -> None:
        self.stops += 1
        if self.fails:
            raise RuntimeError("systemctl failed")
        stop.set()


async def test_a_stop_waits_for_the_runs_in_progress_then_goes_through_the_service_manager():
    runs, manager, stop = _Runs(running=1), _Manager(), asyncio.Event()
    shutdown = Shutdown(runs, stop, manager)
    assert shutdown.request(Ending.STOP) == 1
    await asyncio.sleep(0.01)
    assert not stop.is_set() and shutdown.ending is None
    runs.ended.set()
    await asyncio.wait_for(stop.wait(), 1)
    assert manager.stops == 1 and shutdown.ending is Ending.STOP


async def test_every_app_hears_a_restart_or_stop_is_coming_and_what_it_waits_for():
    heard: list[tuple[Ending, int, bool]] = []
    shutdown = Shutdown(_Runs(running=2), asyncio.Event(), _Manager(), lambda e, n, back: heard.append((e, n, back)))
    shutdown.request(Ending.RESTART)
    shutdown.request(Ending.STOP)
    shutdown.take_back()
    assert heard == [(Ending.RESTART, 2, False), (Ending.STOP, 2, False), (Ending.STOP, 0, True)]
    with pytest.raises(StopRefusedError):
        Shutdown(
            _Runs(), asyncio.Event(), _Manager(refusal="no"), lambda e, n, back: heard.append((e, n, back))
        ).request(Ending.STOP)
    assert len(heard) == 3


async def test_a_restart_never_asks_the_service_manager():
    manager, stop = _Manager(), asyncio.Event()
    shutdown = Shutdown(_Runs(), stop, manager)
    shutdown.request(Ending.RESTART)
    await asyncio.wait_for(stop.wait(), 1)
    assert manager.stops == 0 and shutdown.ending is Ending.RESTART


async def test_the_latest_request_while_waiting_wins():
    runs, manager, stop = _Runs(running=1), _Manager(), asyncio.Event()
    shutdown = Shutdown(runs, stop, manager)
    shutdown.request(Ending.RESTART)
    shutdown.request(Ending.STOP)
    runs.ended.set()
    await asyncio.wait_for(stop.wait(), 1)
    assert shutdown.ending is Ending.STOP


async def test_a_refused_stop_changes_nothing():
    stop = asyncio.Event()
    shutdown = Shutdown(_Runs(), stop, _Manager(refusal="it would start again"))
    with pytest.raises(StopRefusedError, match="it would start again"):
        shutdown.request(Ending.STOP)
    await asyncio.sleep(0.01)
    assert not stop.is_set() and shutdown.ending is None


async def test_a_stop_that_fails_can_be_asked_again():
    manager, stop = _Manager(fails=True), asyncio.Event()
    shutdown = Shutdown(_Runs(), stop, manager)
    shutdown.request(Ending.STOP)
    await asyncio.sleep(0.01)
    assert shutdown.ending is None
    manager.fails = False
    shutdown.request(Ending.STOP)
    await asyncio.wait_for(stop.wait(), 1)
    assert manager.stops == 2 and shutdown.ending is Ending.STOP


async def test_a_pending_restart_is_shown_and_taken_back_and_the_daemon_keeps_running():
    runs, stop = _Runs(running=2), asyncio.Event()
    shutdown = Shutdown(runs, stop, _Manager())
    assert shutdown.pending() is None
    shutdown.request(Ending.RESTART)
    assert shutdown.pending() == Pending(Ending.RESTART, 2)
    shutdown.take_back("web")
    assert shutdown.pending() is None
    runs.ended.set()
    await asyncio.sleep(0.01)
    assert not stop.is_set() and shutdown.ending is None
    with pytest.raises(NoEndingError):
        shutdown.take_back()


async def test_now_cancels_the_runs_a_stop_waits_for_so_it_goes_ahead():
    runs, manager, stop = _Runs(running=3), _Manager(), asyncio.Event()
    shutdown = Shutdown(runs, stop, manager)
    with pytest.raises(NoEndingError):
        shutdown.now()
    shutdown.request(Ending.STOP)
    assert shutdown.now("terminal") == 3
    await asyncio.wait_for(stop.wait(), 1)
    assert manager.stops == 1 and shutdown.ending is Ending.STOP
    assert shutdown.pending() is None
    with pytest.raises(NoEndingError):
        shutdown.take_back()


@pytest.mark.parametrize(
    "env,manager",
    [
        ({}, launchd.Beside if sys.platform == "darwin" else systemd.Beside),
        ({launchd.MANAGED_ENV: "1"}, launchd.Service),
        ({systemd.MANAGED_ENV: "1"}, systemd.Service),
    ],
)
def test_the_service_manager_is_the_one_that_started_the_daemon(monkeypatch, env, manager):
    for name in (launchd.MANAGED_ENV, systemd.MANAGED_ENV):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert isinstance(managers.current(), manager)


async def test_a_daemon_started_by_hand_beside_start_at_boot_on_macos_isnt_stopped_as_launchd_would_restart_it(
    monkeypatch,
):
    on = StartupStatus(enabled=True, managed=False, includes_ollama=False)
    monkeypatch.setattr(launchd, "status", lambda: on)
    assert "Turn start at boot off" in (launchd.Beside().stop_refusal() or "")
    monkeypatch.setattr(launchd, "status", lambda: replace(on, enabled=False))
    assert launchd.Beside().stop_refusal() is None


async def test_a_daemon_started_by_hand_beside_the_systemd_service_stops_its_tries_too(monkeypatch):
    calls: list[tuple[str, ...]] = []

    async def systemctl(*args: str) -> None:
        calls.append(args)

    on = StartupStatus(enabled=True, managed=False, includes_ollama=False, platform="linux")
    monkeypatch.setattr(systemd, "_systemctl", systemctl)
    monkeypatch.setattr(systemd, "status", lambda: on)
    stop = asyncio.Event()
    await systemd.Beside().stop(stop)
    assert stop.is_set() and calls == [("stop", systemd.SERVICE)]
    monkeypatch.setattr(systemd, "status", lambda: replace(on, enabled=False))
    await systemd.Beside().stop(asyncio.Event())
    assert len(calls) == 1


async def test_a_daemon_started_by_hand_stops_by_exiting():
    stop = asyncio.Event()
    assert managers.ByHand().stop_refusal() is None
    await managers.ByHand().stop(stop)
    assert stop.is_set()


def test_a_restart_starts_the_process_again_in_place(monkeypatch):
    execs: list[bool] = []
    monkeypatch.setattr(server, "exec_again", lambda: execs.append(True))
    server.end(Ending.RESTART)
    assert execs == [True]


def test_a_stopped_daemon_exits_cleanly_so_launchd_leaves_it_stopped():
    server.end(Ending.STOP)


def test_a_daemon_that_found_another_running_exits_so_its_service_manager_tries_again():
    with pytest.raises(SystemExit) as exited:
        server.end(None)
    assert exited.value.code == os.EX_TEMPFAIL


async def test_the_log_says_who_asked_for_a_restart_or_stop_and_when_it_goes_ahead(caplog):
    caplog.set_level("INFO", logger="assistant.daemon.shutdown")
    stop = asyncio.Event()
    Shutdown(_Runs(), stop, _Manager()).request(Ending.RESTART, "web (device Mac)")
    await asyncio.wait_for(stop.wait(), 1)
    assert "A restart was asked for by web (device Mac); it waits for 0 run(s) in progress." in caplog.text
    assert "No run in progress: the restart goes ahead." in caplog.text
    with pytest.raises(StopRefusedError):
        Shutdown(_Runs(), asyncio.Event(), _Manager(refusal="launchd would start it again")).request(
            Ending.STOP, "terminal (unix socket)"
        )
    assert "A stop asked for by terminal (unix socket) was refused: launchd would start it again" in caplog.text


def test_the_log_says_which_signal_stopped_the_daemon(caplog):
    caplog.set_level("INFO", logger="assistant.daemon.server")
    stop = asyncio.Event()
    server._stopped_by(signal.SIGTERM, stop)
    assert stop.is_set() and "Stopping: SIGTERM received" in caplog.text


async def test_a_stop_that_takes_long_says_what_it_still_waits_for_and_where(caplog, monkeypatch):
    monkeypatch.setattr(server, "_SLOW_STOP_SECONDS", 0.05)
    caplog.set_level("WARNING", logger="assistant.daemon.server")
    answered = asyncio.Event()

    async def _never_answers() -> None:
        await answered.wait()

    async def memory_writer() -> None:
        await _never_answers()

    quick = asyncio.create_task(asyncio.sleep(0), name="scheduler")
    slow = asyncio.create_task(memory_writer(), name="memory writer")
    waiting = asyncio.create_task(server.until_done([quick, slow]))
    await asyncio.sleep(0.12)
    assert "Still stopping: waiting for memory writer at memory_writer (test_shutdown.py:" in caplog.text
    assert "→ _never_answers (test_shutdown.py:" in caplog.text and "→ wait (locks.py:" in caplog.text
    assert "scheduler" not in caplog.text
    answered.set()
    await asyncio.wait_for(waiting, 1)
