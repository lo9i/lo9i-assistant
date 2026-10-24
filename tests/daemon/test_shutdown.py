"""Restarting or stopping the daemon from the apps (daemon/shutdown.py): what each service manager's daemon
does when stopped (daemon/managers.py), and how the process ends (daemon/server.py::end)."""

import asyncio
import os
import signal

import pytest

from assistant.daemon import launchd, managers, server, systemd
from assistant.daemon.shutdown import Ending, Shutdown
from assistant.protocol import StopRefusedError


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
    heard: list[tuple[Ending, int]] = []
    shutdown = Shutdown(_Runs(running=2), asyncio.Event(), _Manager(), lambda e, n: heard.append((e, n)))
    shutdown.request(Ending.RESTART)
    shutdown.request(Ending.STOP)
    assert heard == [(Ending.RESTART, 2), (Ending.STOP, 2)]
    with pytest.raises(StopRefusedError):
        Shutdown(_Runs(), asyncio.Event(), _Manager(refusal="no"), lambda e, n: heard.append((e, n))).request(
            Ending.STOP
        )
    assert len(heard) == 2


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


@pytest.mark.parametrize(
    "env,manager",
    [
        ({}, managers.ByHand),
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
