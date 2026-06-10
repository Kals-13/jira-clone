from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, REGISTRY, CollectorRegistry
)
import time

# Custom registry to avoid duplicate metric registration
metrics_registry = CollectorRegistry()

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=metrics_registry,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=metrics_registry,
)

http_errors_total = Counter(
    "http_errors_total",
    "Total HTTP errors",
    ["method", "endpoint", "error_code"],
    registry=metrics_registry,
)

websocket_connections_active = Gauge(
    "websocket_connections_active",
    "Active WebSocket connections",
    registry=metrics_registry,
)

websocket_messages_total = Counter(
    "websocket_messages_total",
    "Total WebSocket messages sent",
    ["message_type"],
    registry=metrics_registry,
)

# ── Database metrics ────────────────────────────────────────────────────

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],  # select, insert, update, delete
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
    registry=metrics_registry,
)

# ── Business metrics ────────────────────────────────────────────────────

issues_created_total = Counter(
    "issues_created_total",
    "Total issues created",
    registry=metrics_registry,
)

issues_transitioned_total = Counter(
    "issues_transitioned_total",
    "Total issue status transitions",
    registry=metrics_registry,
)

sprints_completed_total = Counter(
    "sprints_completed_total",
    "Total sprints completed",
    registry=metrics_registry,
)

comments_added_total = Counter(
    "comments_added_total",
    "Total comments added",
    registry=metrics_registry,
)


class MetricsCollector:
    """Helper class to record metric observations."""

    @staticmethod
    def record_http_request(method: str, endpoint: str, status_code: int, duration_seconds: float):
        http_requests_total.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration_seconds)
        if status_code >= 400:
            http_errors_total.labels(method=method, endpoint=endpoint, error_code=status_code).inc()

    @staticmethod
    def record_db_query(operation: str, duration_seconds: float):
        db_query_duration_seconds.labels(operation=operation).observe(duration_seconds)

    @staticmethod
    def set_websocket_connections(count: int):
        websocket_connections_active.set(count)

    @staticmethod
    def record_websocket_message(message_type: str):
        websocket_messages_total.labels(message_type=message_type).inc()

    @staticmethod
    def record_issue_created():
        issues_created_total.inc()

    @staticmethod
    def record_issue_transitioned():
        issues_transitioned_total.inc()

    @staticmethod
    def record_sprint_completed():
        sprints_completed_total.inc()

    @staticmethod
    def record_comment_added():
        comments_added_total.inc()
