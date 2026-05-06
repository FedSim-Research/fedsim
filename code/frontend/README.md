# FedSim Frontend (Angular)

This repository contains the Angular-based frontend for **FedSim (Federated Learning Simulation in Geo-Distributed Settings)**.  
It provides a graph-based UI for configuring, launching, and monitoring federated learning simulations.

---

## Overview

The frontend provides a visual control layer for configuring, launching, and monitoring federated learning simulations.

It supports the following core functions:

- Graph-based editor for defining simulation topologies (e.g., hierarchical federated learning structures)
- Configuration of simulation parameters such as datasets, number of clients, and GPU budget
- Triggering simulation runs via the backend API
- Real-time monitoring and visualization of execution state and results

The application communicates with a FastAPI backend and is served through an Nginx reverse proxy in production deployments.

When running via Docker Compose, the frontend is accessible at:

```
http://<SERVER-IP>:8088
```

This port is defined by the Nginx service configuration in `docker-compose.yml`.

---

## Tech Stack

- Angular 21
- TypeScript
- ngx-vflow (graph editor)
- Vitest (unit testing)

---

## Prerequisites

- Node.js (LTS recommended)
- npm or yarn
- Angular CLI

Install Angular CLI if needed:

```bash
npm install -g @angular/cli
````

---

## Installation

From the frontend directory:

```bash
npm install
```

---

## Development Server

Start the local development server:

```bash
ng serve
```

Then open:

```
http://localhost:4200/
```

The app reloads automatically on file changes.

---

## API Configuration

The frontend expects the backend API to be reachable via configuration in:

```
src/environments/environment.ts
```

Example:

```ts
export const environment = {
  production: false,
  apiUrl: "http://localhost:8088/api"
};
```

For production, adjust accordingly in:

```
environment.prod.ts
```

---

## Code Scaffolding

Generate components:

```bash
ng generate component component-name
```

List schematics:

```bash
ng generate --help
```

---

## Build

Production build:

```bash
ng build
```

Output is stored in:

```
dist/
```

---

## Testing

Run unit tests using Vitest:

```bash
ng test
```

---

## End-to-End Testing

```bash
ng e2e
```

No default framework is enforced; selection is project-specific.

---

## Docker Deployment

In production, the frontend is served via Nginx inside the full FedSim stack.

Default access:

```
http://<SERVER-IP>:8088
```

This is defined in:

```
docker-compose.yml
```

---

## Project Context (FedSim)

This frontend is part of a larger system:

* Backend: FastAPI simulation orchestration
* Framework: Federated learning engines (Hierarchical FL, Spyker FL)
* Infrastructure: Docker-based deployment with optional GPU support

---

## Build Artifacts

Angular build output is generated in:

```
dist/
```