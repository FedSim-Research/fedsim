# pfl-research: simulation framework for accelerating research in Private Federated Learning
Github: https://github.com/apple/pfl-research

**pfl-research** is a Python-based simulation framework designed for **Private Federated Learning (PFL)**. It allows clients to train a global model collaboratively **without sharing their raw data**. The framework is **fast, modular, and easy-to-use**, supporting **TensorFlow, PyTorch, and non-neural network models**.  

## Overview

**Federated Learning (FL)** is a paradigm where multiple clients collaboratively train a machine learning model coordinated by a central server, **without sending their raw data to the server**. Clients can be individual devices (cross-device FL) or data centers representing institutions (cross-silo FL).  

While FL prevents direct data sharing, **model updates alone can still leak sensitive information**, so FL is **not inherently privacy-preserving**.  

**Private Federated Learning (PFL)** enhances FL with privacy mechanisms such as:

- **Secure aggregation:** the server sees only aggregated updates, not individual contributions.  
  *This guarantees the server cannot inspect or reconstruct individual client updates. Secure aggregation usually requires **synchronous FL**, since the server must wait for all updates in a round. Example: if 100 phones train a model, the server only receives the combined update and cannot infer any single device’s contribution.*

- **Differential privacy (DP):** random noise is added to updates to limit information leaked by any single client.  
  *The noise slightly perturbs the update, protecting individual datapoints while still allowing learning of global patterns. DP works in synchronous and asynchronous FL. Example: when training on hospital X-ray data, the noise prevents inferring whether a patient participated.*

**Summary:**  
- **FL:** raw data stays local, but updates may leak information.  
- **PFL:** uses DP + secure aggregation to provide *formal privacy guarantees*.

Because real-world FL deployments are difficult to access and slow for experimentation, **simulation is essential**. FL simulations are computationally heavier than standard ML training due to repeated sampling, local training, and aggregation. Efficient simulators allow realistic experimentation with large-scale federated datasets.

pfl-research addresses these needs by offering:

- **7–72× faster simulation** compared to other FL frameworks  
- **Seamless distributed training** (multi-GPU, multi-host)  
- **Integrated privacy mechanisms**  
- **Support for non-neural models (GBDT, GMM)**  
- **Unified benchmarks for fair, reproducible comparisons**

## Related Work

Many FL frameworks exist—some targeting production with real devices, others targeting simulation. A major limitation of current simulation frameworks is **speed**: slow simulations prevent researchers from running large benchmarks or hyperparameter sweeps.

Most published FL papers still rely on small, unrealistic datasets like CIFAR-10, MNIST, Shakespeare, or LibSVM because **realistic FL datasets are too computationally expensive** for common simulators. Although realistic PFL datasets exist, they are rarely used in practice because current simulators are too slow.

Few frameworks integrate privacy features. Client privacy may be compromised when:

1. A server inspects individual updates before aggregation.  
2. Sensitive information is extracted from the final model.

Issue (2) is addressed by **central DP**, while issue (1) requires **secure aggregation**. Secure aggregation typically reduces updates to a sum, which does not require explicit simulation. However, **DP mechanisms must be simulated**, as noise directly affects optimization stability and accuracy.

Many simulators lack a clean way to plug in DP mechanisms that remain consistent with FL hyperparameters. pfl-research addresses this by tightly integrating modern DP methods with FL workflows.

## System Design

**pfl-research** is implemented entirely in Python and packaged as a single installable module. The framework is highly modular, allowing researchers to select models, algorithms, and optional privacy or compression modules for rapid experimentation.

The simulation algorithm controls:

- sampling cohorts of users,
- defining local optimization logic,
- aggregating statistics,
- and determining stop conditions.

Local outputs (gradients, metrics) can be postprocessed with **DP noise, clipping, weighting, sparsification, or compression**.

pfl-research achieves its performance through several key design principles:

### **1. One persistent model per worker**

Each worker process maintains **exactly one model instance** in GPU memory throughout the entire simulation.  
This model is reused for:

- local training,
- evaluation,
- central updates.

This avoids repeated memory allocation and dramatically improves GPU efficiency.

### **2. In-place parameter updates**

Model parameters are updated **in-place** on the worker’s model instance.  
When the model state must be cloned (e.g., before training the first user in a cohort), the clone is written to **preallocated GPU tensors**, eliminating GPU memory churn.

### **3. No FL topology simulation**

pfl-research **does not simulate** real FL communication patterns, broadcasting, or server-client message flows.  
There is:

- no coordinator process,  
- no broadcasting of updates,  
- no simulated server bottleneck.

Instead, each worker is a **replica** of the global server and executes computation independently until synchronization is necessary.

### **4. End-to-end GPU tensors**

All major operations—including DP mechanisms—use GPU tensors.  
Frameworks like Flower use NumPy (CPU) for outer-loop logic, which slows simulations. pfl-research avoids all unnecessary CPU↔GPU data transfers.

### **5. Load balancing of users**

User datasets vary in size.  
pfl-research uses greedy scheduling based on user weights to distribute users across workers, minimizing stragglers and improving overall throughput.

### **6. Asynchronous data loading**

Through `torch.utils.data` and `tf.data`, user datasets are preloaded and preprocessed asynchronously, allowing GPUs to run at high utilization.

### **Differential Privacy Integration**

pfl-research emphasizes flexible, correct, and efficient DP support:

1. **Pluggable DP mechanisms** (local and central) + pluggable privacy accountants  
2. **Noise is correctly scaled** according to clipping and sampling rates  
3. **DP operations run on GPU** (no CPU transfers)  
4. **Wide library of modern DP methods** provided out-of-the-box  

### **Foundation Model Integration**

Interfaces for training HuggingFace-style models enable state-of-the-art Foundation Model (FM) research in federated and private federated settings.

## Distributed Simulations

Most FL frameworks simulate real-world communication topologies, which leads to significant overhead.  
pfl-research instead simulates **only the computation**.  
Communication happens only when multiple workers need to synchronize aggregated updates.

### **Replica-based execution**

- Every worker is a **full replica** holding its own copy of the global model.  
- No central coordinator exists.  
- Debugging and scaling from 1 to many workers becomes simple and robust.

Workers can reside:

- on a single machine,
- across multiple machines,
- or outnumber GPUs (since FL involves significant non-GPU overhead).

### **Per-iteration workflow**

#### **1. Cohort sampling**
A subset of users is selected.

#### **2. User scheduling**
A greedy scheduler assigns users to workers based on dataset size or weight to minimize straggling.

#### **3. Local training (per worker)**
Each worker:

- clones the model state into preallocated memory if needed,
- trains locally for each assigned user,
- applies postprocessing (clipping, DP noise, quantization, sparsification),
- accumulates updates and metrics into a local aggregate.

#### **4. Local aggregation**
Each worker aggregates updates from its assigned users.

#### **5. Inter-worker aggregation (global all-reduce)**
Workers collectively combine their local aggregates into a single global result.  
This is the **only communication step** per iteration.

#### **6. Global model update**
Each worker applies the global aggregated update to its local model copy.

#### **7. Proceed to next round**
All workers are now synchronized and identical.

## Experiments

This section summarizes the experimental evaluation of **pfl-research**, demonstrating its speed, scalability, and ability to support a wide range of federated learning algorithms and workloads. The experiments compare pfl-research to other popular FL simulators, analyze distributed scaling behavior, and present unified benchmark results with and without Differential Privacy (DP).

## Performance Compared to Other FL Simulators

The authors benchmark multiple frameworks on two representative datasets:

- **CIFAR10 IID** (small-scale, highlights simulation overhead)
- **FLAIR** (large-scale, highlights distributed efficiency)

All frameworks were tested with **identical hyperparameters** for fairness.

### CIFAR10 Results

On a single NVIDIA A100 GPU:

- **pfl-research (PyTorch, 4 worker processes on one GPU)** is the fastest simulator.
- Runtime: **4 minutes 20 seconds**  
  → **7× faster** than Flower  
  → **72× faster** than FedScale

These differences arise because CIFAR10 is small enough that **simulation overhead dominates**, and frameworks that simulate communication or move tensors to CPU incur significant slowdowns.

### FLAIR Results

For the larger FLAIR setup (4× A100 GPUs), the comparison includes **TensorFlow Federated (TFF)** and **Flower**:

- pfl-research again **outperforms both frameworks**, especially as dataset size and model size grow.
- Enabling DP increases runtime by only **~9%**, showing the efficiency of the GPU-accelerated DP pipeline.

### Processes per GPU

The optimal number of worker processes per GPU (**p**) was tuned:

- pfl-research reaches full GPU utilization with **fewer processes** than competing simulators.
- This is due to design decisions such as in-place updates, no topology simulation, and end-to-end GPU tensors.

Overall, pfl-research provides consistently lower wall-clock times across workloads and hardware configurations.

## Scaling Distributed Training

A key advantage of pfl-research is that the number of worker processes is **decoupled** from the number of GPUs. Multiple workers may share a single GPU, which is beneficial because (P)FL workloads tend to have significant non-GPU overhead.

### Scaling with Processes per GPU

For datasets such as CIFAR10 and StackOverflow:

- Increasing to **p = 5** workers/GPU reduces runtime to **~43%** of the baseline (p = 1).

For FLAIR:

- Up to **p = 3** processes fit on one GPU due to model size, still yielding notable speedups.

### Scaling with Number of GPUs

On the StackOverflow benchmark:

- With one GPU (p = 5), runtime is **~3 hours**.
- With **32 GPUs**, runtime drops to **~15 minutes**.

As GPU count increases, speedups naturally taper because fewer users per worker reduce the benefit of load balancing.  
To test a more demanding scenario, the authors increase cohort size to **50,000**, which scales even better:

- Moving from 16 to 32 GPUs increases total GPU-hours by only **3.6%**.

This demonstrates strong and efficient multi-GPU scaling for large federated workloads.

## Unified Benchmarks for Research

pfl-research includes a comprehensive benchmark suite covering:

**Datasets × {IID, non-IID} × {no DP, central DP} × {PyTorch, TensorFlow} × Algorithms**

This unified structure makes it easy to extend benchmarks with new datasets, models, algorithms, or privacy mechanisms.

Experiments were run five times with different seeds; hyperparameters were tuned primarily using FedAvg.

### Algorithm Performance Without DP

The evaluated algorithms include:

- **FedAvg**
- **FedProx**
- **AdaFedProx**
- **SCAFFOLD**

Key observations:

- **FedAvg** provides strong, stable baselines across datasets.
- **FedProx** shows slight benefits on heterogeneous (non-IID) FLAIR, but not consistently.
- **SCAFFOLD**, despite its citation popularity, often performs **worse than FedAvg**, consistent with findings in prior work.

### Algorithm Performance With Central DP

The DP comparison includes:

- **Gaussian mechanism** (PLD accountant)
- **Banded Matrix Factorization (BMF) / DP-FTRL**

Findings:

- **BMF** notably outperforms Gaussian DP on StackOverflow (≈10% relative improvement).
- FedAvg, FedProx, and AdaFedProx behave similarly under DP noise.
- **SCAFFOLD degrades significantly** under DP, especially on FLAIR.

### LLM Benchmarks

pfl-research also supports federated fine-tuning of larger models. Benchmarks include:

- **Stanford Alpaca (IID partition)**
- **Aya (natural annotator-based non-IID partitions)**
- **OpenAssistant (user-identified non-IID conversational data)**

Aya and OA provide realistic heterogeneous partitions, making them well suited for practical FL evaluation.  
These results show that pfl-research scales to **modern, large-model workloads**, including instruction-tuned LLMs.

---

**Summary:**  
pfl-research demonstrates:

- **7–72× speedups** over existing FL simulators  
- **Efficient scaling** across worker processes and GPUs  
- **Robust, reproducible baselines** for numerous FL and PFL algorithms  
- **Support for large-scale models**, including LLMs  
- **Minimal overhead when enabling DP**

Overall, the experiments validate pfl-research as a fast, scalable, and flexible simulator for modern federated learning research.