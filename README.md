### Edge Sensor Observability Stack

This project implements a **lightweight, production-ready observability stack** for a Python-based sensor service running on a **resource-constrained edge robot module**.

- **Sensor service**: Python 3.11 + Flask + Gunicorn
- **Metrics**: Prometheus + `prometheus-client` + `psutil`
- **Visualization**: Grafana OSS (pre-provisioned)
- **Orchestration**: Docker Compose

The design is optimized for a device with **2 CPU cores** and **≈500 MB usable RAM**, with the entire observability stack constrained to **< 300 MB RAM**.

---

### Architecture Overview

- **sensor-service**
  - Lightweight Flask API served by Gunicorn.
  - Exposes:
    - `/sensor` – simulated sensor readings.
    - `/metrics` – Prometheus metrics (fast, <100ms target).
    - `/health` – simple health check.
  - Exposes custom metrics for events, latency, queue depth, and failures, plus CPU and memory usage.

- **Prometheus**
  - Scrapes `sensor-service:8000/metrics` every **15s** with a **5s** timeout.
  - Configured with:
    - **2h retention**.
    - **WAL compression** enabled.
    - Persistent storage via Docker volume.

- **Grafana**
  - OSS image with:
    - Anonymous **read-only** access enabled.
    - Pre-provisioned Prometheus datasource.
    - Pre-provisioned dashboard for the sensor service.

---

### Resource Budget (High Level)

- **Sensor service**: target **≤ 40 MB** RAM, limited via Docker.
- **Prometheus**: limit **120 MB** RAM, tuned retention and WAL compression.
- **Grafana**: limit **120 MB** RAM, minimal dashboards and plugins.
- **Docker overhead**: stays below **20 MB** in practice.

This keeps the **total stack under 300 MB**, suitable for edge deployments.

---

### Custom Metrics Exposed

All metrics are exposed at `http://localhost:8000/metrics` (inside Docker: `http://sensor-service:8000/metrics`).

- **Counter** `sensor_events_total`  
  Counts successfully processed sensor events.

- **Histogram** `sensor_processing_seconds`  
  Measures per-request processing time for the sensor endpoint, with buckets tuned for sub-second latencies.

- **Gauge** `sensor_queue_depth`  
  Represents the simulated sensor queue size (a proxy for load and backpressure).

- **Counter** `sensor_failures_total`  
  Counts failed sensor readings (errors and simulated failures).

- **Gauge** `sensor_service_cpu_percent`  
  CPU usage (%) for the sensor service process (from `psutil`).

- **Gauge** `sensor_service_memory_bytes`  
  RSS memory usage in bytes for the sensor service process.

These metrics drive the pre-built Grafana dashboard.

---

### Running the Stack

Requirements:

- Docker
- Docker Compose

From the `devops_edge_assignment` directory:

```bash
docker compose up --build
```

This will start:

- `sensor-service` on `http://localhost:8000`
- `prometheus` on `http://localhost:9090`
- `grafana` on `http://localhost:3000`

To stop:

```bash
docker compose down
```

---

### Endpoints

- **Sensor API**
  - `GET /sensor`
    - Simulated sensor response with:
      - `status` (`ok` or `error`)
      - `value` (random float for successful reads)
      - `queue_depth`

- **Health**
  - `GET /health`
    - Simple JSON health report (`{"status": "healthy"}`) with HTTP 200.

- **Metrics**
  - `GET /metrics`
    - Prometheus exposition format.
    - Includes custom sensor metrics and process CPU/memory gauges.

---

### Grafana Dashboard

Once the stack is running, open Grafana:

- URL: `http://localhost:3000`
- Authentication:
  - Anonymous access is enabled with **Viewer** role.

Dashboard: **Edge Sensor Observability**

It provides:

- **CPU Usage**: `sensor_service_cpu_percent`
- **Memory Usage**: `sensor_service_memory_bytes` (converted to MB)
- **Sensor Event Rate**: `rate(sensor_events_total[1m])`
- **Latency (p50/p90/p99)**: derived from `sensor_processing_seconds` histogram
- **Queue Depth**: `sensor_queue_depth`
- **Failure Rate**: `rate(sensor_failures_total[5m])`

This gives a concise, real-time view of:

- Service health and responsiveness
- Resource utilization on constrained hardware
- Reliability (error/failure behavior)

---

### Performance & Reliability Notes

- `/metrics` is explicitly designed to respond in **<100ms** on edge hardware:
  - No heavy CPU loops.
  - No large per-request allocations.
  - Logs a warning when scrapes exceed 100ms to catch regressions early.
- Prometheus scrape interval and retention are tuned to:
  - Limit memory and CPU usage.
  - Still provide enough resolution for operational decisions and alerting.
- Grafana uses:
  - Minimal configuration and plugins.
  - A focused dashboard to reduce footprint.

For deeper details on optimization decisions and trade-offs, see `PERFORMANCE_REPORT.md`.

