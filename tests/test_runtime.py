from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from fedsim import runtime


@pytest.fixture
def ray_state(monkeypatch):
    assert runtime._active_users == 0
    state = SimpleNamespace(initialized=False)

    def initialize(**kwargs):
        state.initialized = True

    def shutdown():
        assert runtime._active_users == 0
        state.initialized = False

    monkeypatch.setattr(runtime.ray, "is_initialized", lambda: state.initialized)
    monkeypatch.setattr(runtime.ray, "init", Mock(side_effect=initialize))
    monkeypatch.setattr(runtime.ray, "shutdown", Mock(side_effect=shutdown))
    yield state
    assert runtime._active_users == 0


def test_nested_users_keep_runtime_alive_until_last_exit(ray_state):
    with runtime.managed_ray_runtime():
        runtime.ray.init.assert_not_called()
        runtime.ensure_ray_initialized()
        with runtime.managed_ray_runtime():
            runtime.ensure_ray_initialized()
        runtime.ray.shutdown.assert_not_called()
        assert ray_state.initialized
    runtime.ray.init.assert_called_once()
    runtime.ray.shutdown.assert_called_once()
    assert not ray_state.initialized


def test_failed_user_releases_runtime_and_next_run_can_start(ray_state):
    with pytest.raises(ValueError, match="run failed"):
        with runtime.managed_ray_runtime():
            runtime.ensure_ray_initialized()
            raise ValueError("run failed")
    assert not ray_state.initialized
    with runtime.managed_ray_runtime():
        runtime.ensure_ray_initialized()
    assert runtime.ray.init.call_count == runtime.ray.shutdown.call_count == 2


def test_unused_runtime_is_not_initialized_or_shut_down(ray_state):
    with runtime.managed_ray_runtime():
        pass
    runtime.ray.init.assert_not_called()
    runtime.ray.shutdown.assert_not_called()


def test_initialization_reads_actual_ray_state_instead_of_cached_flag(ray_state):
    runtime.ensure_ray_initialized()
    # Model an external ray.shutdown() between standalone engine calls.
    ray_state.initialized = False
    runtime.ensure_ray_initialized()
    assert runtime.ray.init.call_count == 2


def test_initialization_falls_back_to_local_runtime(ray_state):
    initialize = runtime.ray.init.side_effect
    runtime.ray.init.side_effect = [ConnectionError("no cluster"), None]
    runtime.ensure_ray_initialized()
    assert runtime.ray.init.call_args_list == [
        call(address="auto", ignore_reinit_error=True, include_dashboard=True),
        call(ignore_reinit_error=True, include_dashboard=True),
    ]
    runtime.ray.init.side_effect = initialize


def test_explicit_shutdown_refuses_to_interrupt_managed_user(ray_state):
    with runtime.managed_ray_runtime():
        runtime.ensure_ray_initialized()
        with pytest.raises(RuntimeError, match="fedsim_runtime_in_use"):
            runtime.shutdown_ray()
        assert ray_state.initialized
        runtime.ray.shutdown.assert_not_called()
    runtime.ray.shutdown.assert_called_once()


def test_new_user_cannot_enter_during_final_shutdown(monkeypatch, ray_state):
    closing = Event()
    finish_shutdown = Event()
    attempting_entry = Event()
    entered = Event()
    shutdown = runtime.ray.shutdown.side_effect

    def slow_shutdown():
        closing.set()
        assert finish_shutdown.wait(5)
        shutdown()

    monkeypatch.setattr(runtime.ray, "shutdown", Mock(side_effect=slow_shutdown))

    def old_user():
        with runtime.managed_ray_runtime():
            runtime.ensure_ray_initialized()

    def new_user():
        attempting_entry.set()
        with runtime.managed_ray_runtime():
            entered.set()
            runtime.ensure_ray_initialized()

    with ThreadPoolExecutor(max_workers=2) as threads:
        old = threads.submit(old_user)
        try:
            assert closing.wait(5)
            new = threads.submit(new_user)
            assert attempting_entry.wait(5)
            assert not entered.wait(0.1)
        finally:
            finish_shutdown.set()
        old.result(timeout=5)
        new.result(timeout=5)
    assert entered.is_set()
    assert runtime.ray.init.call_count == runtime.ray.shutdown.call_count == 2
