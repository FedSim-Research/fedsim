# Hierarchical Simulation API Guide

This guide explains how to use the `HierarchicalSimulation` class to configure and run hierarchical federated learning simulations. This system allows you to define complex topologies with Super Servers, Edge Servers, and Clients, running on top of the Ray framework.

## Getting Started

The simulation logic is located in `main_hierarchical.py`.

### 1. Import Dependencies

```python
from main.main_hierarchical import HierarchicalSimulation
from specs.performance_metrics import Performance
from specs.network_metrics import Network
```

### 2. Initialize the Simulation

Create an instance of the simulation container. You can specify a runtime limit (in simulation seconds).

```python
# Run for 5000 simulation seconds
sim = HierarchicalSimulation(run_time_limit=5000.0)
```

### 3. Define Metrics

Define the capabilities of your simulated hardware and network conditions using the `Performance` and `Network` specifications.

#### Performance
Controls the computation speed and variability.
*   `compute_factor` (float): A specific speed multiplier. Training time = `workload / compute_factor`. Higher values mean faster nodes (e.g. GPU vs CPU).
*   `performance_stddev` (float): Standard deviation for calculation time noise (to simulate load fluctuations).

```python
# Performance(compute_factor, performance_stddev)
high_end_gpu = Performance(compute_factor=10.0, performance_stddev=0.5) 
legacy_cpu = Performance(compute_factor=2.0, performance_stddev=1.0)
```

#### Network
Controls data transmission latency and reliability. Bandwidth is defined per-node.
*   `latency_avg` (int): Average latency in milliseconds.
*   `latency_stddev` (int): Jitter or standard deviation of latency in milliseconds.
*   `packet_loss_avg` (float): Average packet loss probability (0.0 to 1.0).
*   `packet_loss_stddev` (float): Standard deviation of packet loss.

```python
# Network(latency_avg, latency_stddev, packet_loss_avg, packet_loss_stddev)
fiber_internet = Network(
    latency_avg=20, 
    latency_stddev=5, 
    packet_loss_avg=0.001, 
    packet_loss_stddev=0.0001
)

unstable_3g = Network(
    latency_avg=150, 
    latency_stddev=50, 
    packet_loss_avg=0.05, 
    packet_loss_stddev=0.01
)
```

### 4. Configure Components

You must configure the hierarchy in top-down order (Super Server -> Edge Servers -> Clients).

#### Set Super Server
Network metrics are omitted for the Super Server since they are provided through the edge servers.

```python
sim.set_super_server(
    server_id="super_server",
    name="Main Coordinator",
    perf=high_end_gpu,
    upload_speed=1000.0,    # Mbps
    download_speed=400.0,  # Mbps
    training_config={"epochs": 1, "lr": 0.01}
)
```

#### Add Edge Servers
Edge servers require a dictionary mapping connected Node IDs (Super Server and Clients) to the `Network` conditions of that link.

```python
# Keys map to the IDs of the nodes this edge server communicates with.
# Usually, this includes the Super Server and its assigned Clients.
network_map = {
    "super_server": fiber_internet,
    "client_0": unstable_3g,
    # "client_1": ...
}

sim.add_edge_server(
    server_id="edge_1", 
    name="Edge Node 1", 
    perf=high_end_gpu, 
    net=network_map,
    upload_speed=100.0,    # Mbps
    download_speed=500.0   # Mbps
)
```

#### Add Clients
Clients must be assigned to an existing Edge Server. The `dataset_partition_id` determines which slice of the CIFAR-10 data the client receives. Link quality is defined at the Edge Server level.

```python
sim.add_client(
    client_id="client_0",
    edge_id="edge_1",      # Must match an added edge server ID
    name="Client 0",
    perf=legacy_cpu,
    upload_speed=2.0,      # Mbps
    download_speed=10.0,   # Mbps
    dataset_partition_id=0,
    total_partitions=10
)
```

### 5. Build and Run

Once configured, build the environment (starts Ray actors) and run the loop.

```python
# Spawns actors and wires connections
sim.build()

# Starts the simulation event loop
sim.run()
```

### 6. Save and Evaluate

After the simulation finishes, you can extract the global model and evaluate it.

```python
# Save weights to disk
sim.save_model("my_model.pth")

# Run evaluation on test set (uses main_hierarchical.evaluate_model)
from main.main_hierarchical import evaluate_model
evaluate_model("my_model.pth")
```

## Quick Start
To see the system in action with a default topology (1 Super, 2 Edges, 4 Clients), you can run the default function:

```python
from main.main_hierarchical import run_default_simulation

run_default_simulation()
```
