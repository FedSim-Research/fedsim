"""Smoke test: default vs. fixed Spyker on 20 IID clients, 2 servers, short horizon."""

import sys
from collections import OrderedDict

import ray
import torch
from datasets import load_dataset
from torch.utils.data import DataLoader

from fedsim.engines.spyker.simulation import SpykerSimulation
from fedsim.learning import Net, apply_transforms, test
from fedsim.settings import dataset_cache_dir
from fedsim.specs.network_metrics import Network
from fedsim.specs.performance_metrics import Performance

VARIANTS = {
    "default": {},
    "fixed": {"decay_mode": "relative", "staleness_mode": "delta", "h_inter": "auto"},
}
CLIENTS, SERVERS, HORIZON, SEED = 20, 2, float(sys.argv[2]) if len(sys.argv) > 2 else 60.0, 42


def run(name):
    sim = SpykerSimulation(seed=SEED)
    sim.set_configurations(
        VARIANTS[name], {"local_epochs": 1, "learning_rate": 0.01}, {"run_time_limit": HORIZON}
    )
    sim.set_metadata(run_id=f"smoke-{name}", graph_id="0", eval_interval=0.0)
    servers = [f"s{i}" for i in range(SERVERS)]
    clients = {s: [f"{s}-c{j}" for j in range(CLIENTS // SERVERS)] for s in servers}
    for s in servers:
        net = {p: Network(100, 0, 0, 0) for p in servers if p != s}
        net.update({c: Network(10, 0, 0, 0) for c in clients[s]})
        sim.add_server(s, s, Performance(500, 0), net, 100, 100)
    index = 0
    for s in servers:
        for c in clients[s]:
            sim.add_client(
                c, s, c, Performance(500, 0), index, CLIENTS, 100, 100, seed=SEED + index
            )
            index += 1
    sim.build()
    sim.run()
    weights = ray.get([sim.spyker_actors_map[s].get_global_model.remote() for s in servers])
    sim.close()
    split = load_dataset(sim.dataset_id, split="test", cache_dir=str(dataset_cache_dir()))
    loader = DataLoader(split.with_transform(apply_transforms), batch_size=256)
    model, accs = Net(), []
    for arrays in weights:
        state = OrderedDict(zip(model.state_dict().keys(), map(torch.tensor, arrays)))
        model.load_state_dict(state)
        accs.append(test(model, loader, torch.device("cpu"))[1])
    print(f"RESULT {name}: mean acc {sum(accs) / len(accs):.4f} per server {accs}", flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
