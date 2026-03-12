import logging
import random
import time
from typing import Dict, Any

import psutil
from flask import Flask, jsonify, Response, request
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    CONTENT_TYPE_LATEST,
    generate_latest,
)


app = Flask(__name__)


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("sensor_service")


# -----------------------------------------------------------------------------
# Process information (for CPU / memory metrics)
# -----------------------------------------------------------------------------
process = psutil.Process()


# -----------------------------------------------------------------------------
# Custom metrics
# -----------------------------------------------------------------------------

# Total number of successfully processed sensor events
SENSOR_EVENTS_TOTAL = Counter(
    "sensor_events_total", "Counts processed sensor events.",
)

# Histogram of sensor processing time
SENSOR_PROCESSING_SECONDS = Histogram(
    "sensor_processing_seconds",
    "Histogram of sensor processing time.",
    # Buckets tuned for a fast edge service (up to ~1s)
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# Simulated sensor queue depth
SENSOR_QUEUE_DEPTH = Gauge(
    "sensor_queue_depth", "Simulated sensor queue depth.",
)

# Total number of failed sensor readings
SENSOR_FAILURES_TOTAL = Counter(
    "sensor_failures_total", "Counts failed sensor readings.",
)

# Resource usage for Grafana dashboarding
SERVICE_CPU_PERCENT = Gauge(
    "sensor_service_cpu_percent",
    "Sensor service process CPU usage (percent).",
)
SERVICE_MEMORY_BYTES = Gauge(
    "sensor_service_memory_bytes",
    "Sensor service process RSS memory usage in bytes.",
)


def _update_resource_metrics() -> None:
    """Update CPU and memory gauges using psutil without heavy operations."""
    # cpu_percent with interval=None is non-blocking and uses last interval
    cpu_percent = process.cpu_percent(interval=None)
    SERVICE_CPU_PERCENT.set(cpu_percent)

    mem_info = process.memory_info()
    SERVICE_MEMORY_BYTES.set(mem_info.rss)


@app.route("/metrics")
def metrics() -> Response:
    """
    Expose Prometheus metrics.

    Designed to be very fast (<100ms) and non-blocking to avoid scrape failures.
    """
    start = time.perf_counter()

    _update_resource_metrics()

    data = generate_latest()
    elapsed = time.perf_counter() - start

    if elapsed > 0.1:
        logger.warning("Slow /metrics scrape: %.3f seconds", elapsed)

    return Response(data, mimetype=CONTENT_TYPE_LATEST)


@app.route("/sensor")
def sensor() -> Response:
    """
    Simulated sensor endpoint.

    - Updates queue depth gauge.
    - Records processing latency in histogram.
    - Increments success/failure counters.
    """
    start = time.perf_counter()

    # Simulated queue depth in a small, bounded range
    queue_depth = random.randint(0, 100)
    SENSOR_QUEUE_DEPTH.set(queue_depth)

    try:
        # Simulate a small chance of failure
        if random.random() < 0.1:
            SENSOR_FAILURES_TOTAL.inc()
            duration = time.perf_counter() - start
            SENSOR_PROCESSING_SECONDS.observe(duration)
            payload: Dict[str, Any] = {
                "status": "error",
                "error": "simulated sensor failure",
                "queue_depth": queue_depth,
            }
            return jsonify(payload), 500

        # Simulate lightweight processing without heavy CPU or memory use
        simulated_value = random.uniform(0.0, 1.0)

        SENSOR_EVENTS_TOTAL.inc()
        duration = time.perf_counter() - start
        SENSOR_PROCESSING_SECONDS.observe(duration)

        payload = {
            "status": "ok",
            "value": simulated_value,
            "queue_depth": queue_depth,
        }
        return jsonify(payload)
    except Exception as exc:  # pragma: no cover - defensive logging
        SENSOR_FAILURES_TOTAL.inc()
        logger.exception("Unexpected error in /sensor: %s", exc)
        duration = time.perf_counter() - start
        SENSOR_PROCESSING_SECONDS.observe(duration)
        return jsonify({"status": "error", "error": "internal error"}), 500


@app.route("/health")
def health() -> Response:
    """Simple health check endpoint."""
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    # Development entrypoint. In containers we use gunicorn.
    app.run(host="0.0.0.0", port=8000, threaded=True)
