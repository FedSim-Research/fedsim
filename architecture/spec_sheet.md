# Architecture Spec Sheet

## Performance Metrics
- support for different presets (e.g. mobile device, desktop pc) as well as custom options
- `aggregation model`
- `cpu count` and `gpu count`, as percentage
- `internal calculation time`

<br>

## Network Metrics
- `avg latency`
- `avg packet loss`
- `bandwidth`, e.g. semaphore with `n` permits

<br>

## Client
### Client Spec
- `id`
- `name`
- [`device type`](#performance-metrics)
- [`network properties`](#network-metrics)

### Client Bucket
- `list<id>`
- `quantity`
- [`client spec`](#client)

<br>

## Server
### Server Spec
- `id`
- `name`
- [`device type`](#performance-metrics)
- [`network properties`](#network-metrics)

### Server Bucket
- `list<id>`
- `quantity`
- [`server spec`](#server)
