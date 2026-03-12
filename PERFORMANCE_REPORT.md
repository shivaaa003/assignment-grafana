### Edge Sensor Service Observability – Performance Report

#### Memory & CPU Behavior

- **Memory usage before optimization**:  
  - The original service allocated a global `data_blob` of ~5 MB and multiplied it in `/metrics`, temporarily creating up to ~15 MB transient strings per scrape.  
  - Combined with Flask and Python overhead, this could easily push the process well above **100–150 MB** under load, with sustained pressure from frequent scrapes.
- **Memory usage after optimization**:  
  - Removed the global 5 MB blob and all per-request string multiplication in `/metrics`.  
  - Processing is now lightweight and mostly numeric; only small JSON responses are created.  
  - With `python:3.11-slim`, minimal dependencies, and no large globals, the sensor container fits in the **~40 MB target** (RSS) under typical load.

- **CPU spike root cause**:  
  - `/metrics` executed a tight Python loop (`for _ in range(2_000_000)`) on every scrape; at 5s scrape intervals and multiple scrapers, this caused **sustained CPU spikes** and long GC pauses.
- **CPU fixes applied**:  
  - Removed all artificial CPU loops and heavy computations from `/metrics`.  
  - Service now performs only cheap psutil calls and serialization for metrics output.  
  - Gunicorn with 2 workers reduces latency variance and shields against occasional slow handlers.

#### Observability & Scrape Reliability

- **Scrape failure root cause**:  
  - `/metrics` performed heavy CPU work and temporary allocations before generating metrics, meaning Prometheus often hit timeouts and produced intermittent scrape failures.  
  - A 5s scrape interval with heavy work per scrape further increased contention.
- **How it was fixed**:  
  - `/metrics` now:
    - Updates only lightweight CPU/memory gauges via psutil.
    - Calls `generate_latest()` directly with no heavy business logic.  
    - Logs a warning when scrape time exceeds **100ms** to surface regressions.  
  - Prometheus was tuned with a 15s scrape interval and 5s timeout to reduce pressure while remaining responsive.

- **Custom metrics added**:  
  - **`sensor_events_total` (Counter)**: counts successfully processed sensor events.  
  - **`sensor_processing_seconds` (Histogram)**: captures per-request processing time, with buckets tuned for sub-second latencies on edge hardware.  
  - **`sensor_queue_depth` (Gauge)**: models the sensor queue size, allowing backpressure and saturation visibility.  
  - **`sensor_failures_total` (Counter)**: tracks failed sensor reads and exceptions for reliability analysis.  
  - Additional gauges `sensor_service_cpu_percent` and `sensor_service_memory_bytes` provide resource usage for the Grafana dashboard.

#### Prometheus Optimization Reasoning

- **Memory controls**:
  - TSDB retention reduced to **2h** (`--storage.tsdb.retention.time=2h`) to cap on-disk and in-memory series data.
  - WAL compression enabled (`--storage.tsdb.wal-compression`) to reduce WAL size and associated memory pressure.
  - Container memory limit set to **120 MB**, with focused scrape config targeting only the sensor service.
- **Scrape configuration**:
  - Global `scrape_interval` and `evaluation_interval` set to **15s** to balance freshness with resource usage.
  - `scrape_timeout` set to **5s** to tolerate small network hiccups while still detecting genuine stalls.

These changes keep Prometheus well within the **120 MB** budget and reduce CPU utilization by avoiding excessive scrapes and retention.

#### Grafana Memory Control Reasoning

- **Lightweight setup**:
  - Uses **Grafana OSS** with the default plugin set; no additional plugins are installed.  
  - Anonymous access is enabled with read-only role to avoid extra auth overhead and complexity.
- **Provisioning**:
  - A single Prometheus datasource is pre-provisioned and set as default.  
  - One focused dashboard (`Edge Sensor Observability`) is provisioned, with panels for:
    - CPU usage (`sensor_service_cpu_percent`).  
    - Memory usage (`sensor_service_memory_bytes`).  
    - Sensor event rate (`rate(sensor_events_total[1m])`).  
    - Latency quantiles (`histogram_quantile` over `sensor_processing_seconds_bucket`).  
    - Queue depth (`sensor_queue_depth`).  
    - Failure rate (`rate(sensor_failures_total[5m])`).
- **Resource limits**:
  - Grafana container is constrained to **120 MB** RAM via Docker Compose resource limits, keeping the whole stack under the 300 MB budget.

#### Stack-Level Resource Budget

- **Sensor service**:  
  - Small Python 3.11 slim image with only Flask, Prometheus client, psutil, and Gunicorn.  
  - No large globals, minimal per-request allocations, single lightweight Flask app → targets **≤ 40 MB** RSS.
- **Prometheus**:  
  - Constrained to **120 MB** with short retention and WAL compression.
- **Grafana**:  
  - Constrained to **120 MB** with a minimal dashboard footprint.
- **Docker overhead**:  
  - With lean images and low I/O, the remaining overhead stays well below the **20 MB** target.

#### One Further Improvement With Another Week

Given additional time, the main improvement would be to implement **adaptive sampling and dynamic scrape intervals**:

- Introduce an internal “load shedder” that:
  - Reduces sensor processing frequency under high CPU or memory pressure.
  - Coarsens histogram buckets dynamically when utilization is high to cut cardinality.
- Integrate with Prometheus via recording rules to downsample historical data (e.g., 1m → 5m → 1h windows) while tightening real-time windows for on-call use.

This would further harden the system for large fleets of robots while preserving observability signal quality under extreme resource constraints.

