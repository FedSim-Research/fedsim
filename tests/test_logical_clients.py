import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import ray
import torch
from torch.utils.data import DataLoader

from fedsim.clients import training
from fedsim.clients.actor import VirtualClient
from fedsim.clients.handle import ClientHandle
from fedsim.simulation.context import SimulationContext
from fedsim.simulation.cpu_execution import CpuExecutionPool, CpuExecutionWorker
from fedsim.specs.client_spec import ClientSpec
from fedsim.specs.network_metrics import Network
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec


def make_context(seed, speed=500):
    clients = {
        name: ClientSpec(name, name, Performance(speed, 0.1), 20, 30)
        for name in ("client-0", "client-1")
    }
    links = {name: Network(20, 3, 0.03, 0.01) for name in clients}
    server = ServerSpec("server", "server", Performance(1000, 0), links, 40, 50)
    return SimulationContext(None, clients, {"server": server}, seed=seed)


def make_handle(context, partition=0):
    return ClientHandle(
        context.execution_id,
        f"client-{partition}",
        {
            "dataset_partition_id": partition,
            "total_partitions": 2,
            "seed": context.seed + partition,
        },
        context,
    )


def test_interleaved_worker_clients_match_independent_clients_exactly(monkeypatch):
    """Actual SGD, loader-generator advancement and noisy timing survive reuse."""
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    get = Mock(side_effect=lambda value: value)
    monkeypatch.setattr(ray, "get", get)
    monkeypatch.setattr(ray, "put", lambda arrays: [array.copy() for array in arrays])

    def load_data(partition_id, num_partitions, seed=None, **kwargs):
        generator = torch.Generator().manual_seed(100 + partition_id)
        samples = [
            {"img": torch.rand((3, 32, 32), generator=generator), "label": index % 10}
            for index in range(9)
        ]
        return DataLoader(
            samples, batch_size=32, shuffle=True, generator=torch.Generator().manual_seed(seed)
        ), DataLoader(samples, batch_size=32)

    monkeypatch.setattr(training, "load_data", load_data)
    contexts = [make_context(42), make_context(17, speed=100)]
    handles = [make_handle(context, partition) for context in contexts for partition in range(2)]
    standalone = [VirtualClient(h.client_id, h.client_config, h.context_ref) for h in handles]
    worker = CpuExecutionWorker.__ray_metadata__.modified_class()
    initial = {
        handle.execution_id: [array.copy() for array in client.inner_client.get_parameters()]
        for handle, client in zip(handles, standalone, strict=True)
        if handle.client_config["dataset_partition_id"] == 0
    }
    create_model = Mock(wraps=training.Net)
    monkeypatch.setattr(training, "Net", create_model)
    for sequence, index in enumerate([0, 1, 2, 0, 3, 1, 2, 0]):
        payload = {
            "event_type": "START_FIT",
            "trigger_time": sequence * 10,
            "data": {
                "server_id": "server",
                "server_ref": "server-handle",
                "config": {"epochs": 1, "lr": 0.01, "batch_size": 3, "model_age": sequence},
            },
        }
        parameters = initial[handles[index].execution_id]
        expected = standalone[index].handle_event(payload, direct_refs=parameters)[0]
        actual = worker.call(
            handles[index], "handle_event", (payload,), {"direct_refs": parameters}
        )[0]
        assert actual[:4] == expected[:4]
        for observed, reference in zip(actual[4], expected[4], strict=True):
            np.testing.assert_array_equal(observed, reference)
    assert len(worker._clients) == 4
    assert get.call_count == 2
    assert create_model.call_count == 1
    assert len({id(client.inner_client.net) for client in worker._clients.values()}) == 1
    for handle, reference in zip(handles, standalone, strict=True):
        client = worker._clients[(handle.execution_id, handle.client_id)]
        assert torch.equal(
            client.inner_client.trainloader.generator.get_state(),
            reference.inner_client.trainloader.generator.get_state(),
        )
    worker.release_clients(contexts[0].execution_id)
    assert {key[0] for key in worker._clients} == {contexts[1].execution_id}
    assert set(worker._contexts) == {contexts[1].execution_id}


def test_worker_rejects_a_mismatched_client_context(monkeypatch):
    context = make_context(42)
    handle = make_handle(context)
    handle = ClientHandle("another-run", handle.client_id, handle.client_config, context)
    monkeypatch.setattr(ray, "get", lambda value: value)
    worker = CpuExecutionWorker.__ray_metadata__.modified_class()
    with pytest.raises(ValueError, match="identity"):
        worker.call(handle, "handle_event", ({},), {})
    assert worker._clients == {}


def test_client_handle_does_not_submit_work_without_cpu_admission():
    with pytest.raises(RuntimeError, match="CPU execution pool"):
        make_handle(make_context(42)).handle_event({})


def test_pool_preserves_affinity_and_cpu_bound_across_clients_and_evaluators(monkeypatch):
    from fedsim.simulation import cpu_execution

    async def scenario():
        active = peak = 0
        owners = {}

        def worker(index):
            async def call(actor, method, args, kwargs):
                nonlocal active, peak
                active += 1
                peak = max(active, peak)
                if isinstance(actor, ClientHandle):
                    key = (actor.execution_id, actor.client_id)
                    assert owners.setdefault(key, index) == index
                await asyncio.sleep(0.005)
                active -= 1
                return index

            return SimpleNamespace(call=SimpleNamespace(remote=call))

        workers = iter([worker(0), worker(1)])
        monkeypatch.setattr(cpu_execution.CpuExecutionWorker, "remote", lambda: next(workers))
        pool = CpuExecutionPool.__ray_metadata__.modified_class(2)
        handles = [make_handle(make_context(42), index % 2) for index in range(6)]
        clients = [pool.call(handle, "handle_event", ({},), {}) for handle in handles * 2]
        evaluators = [pool.call("evaluator", "evaluate", (), {}) for _ in range(3)]
        results = await asyncio.gather(*(clients + evaluators))
        assert results[:12] == [index % 2 for index in range(6)] * 2
        assert peak == 2

    asyncio.run(scenario())


def test_release_drains_active_calls_and_rejects_queued_and_future_calls(monkeypatch):
    from fedsim.simulation import cpu_execution

    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        released = []

        async def call(*args):
            started.set()
            await finish.wait()
            return "completed"

        async def release(execution_id):
            released.append(execution_id)

        worker = SimpleNamespace(
            call=SimpleNamespace(remote=call), release_clients=SimpleNamespace(remote=release)
        )
        monkeypatch.setattr(cpu_execution.CpuExecutionWorker, "remote", lambda: worker)
        pool = CpuExecutionPool.__ray_metadata__.modified_class(1)
        handle = make_handle(make_context(42))
        active = asyncio.create_task(pool.call(handle, "handle_event", ({},), {}))
        await started.wait()
        queued = asyncio.create_task(pool.call(handle, "handle_event", ({},), {}))
        closing = asyncio.create_task(pool.release_clients(handle.execution_id))
        await asyncio.sleep(0)
        assert not closing.done()
        finish.set()
        assert await active == "completed"
        with pytest.raises(RuntimeError, match="released"):
            await queued
        await closing
        with pytest.raises(RuntimeError, match="released"):
            await pool.call(handle, "handle_event", ({},), {})
        assert released == [handle.execution_id]
        # An independently running controller retains access to the same pool.
        other = make_handle(make_context(17))
        assert await pool.call(other, "handle_event", ({},), {}) == "completed"

    asyncio.run(scenario())
