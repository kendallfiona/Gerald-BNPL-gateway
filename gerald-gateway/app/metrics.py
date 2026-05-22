import time
from contextlib import contextmanager

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

REQUESTS = Counter(
    "service_gerald_gateway_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
ERRORS = Counter(
    "service_gerald_gateway_errors_total",
    "Total application errors",
    ["endpoint", "error_type"],
)
REQUEST_LATENCY = Histogram(
    "service_gerald_gateway_request_duration_seconds",
    "HTTP request latency",
    ["endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
APPROVED = Counter("gerald_approved_total", "Approved BNPL decisions")
DECLINED = Counter("gerald_declined_total", "Declined BNPL decisions")
CREDIT_LIMIT_BUCKET = Counter(
    "gerald_credit_limit_bucket_total",
    "Credit limit bucket distribution",
    ["bucket"],
)
BANK_FETCH_FAILURES = Counter("bank_fetch_failures_total", "Bank API fetch failures")
WEBHOOK_LATENCY = Histogram(
    "webhook_latency_seconds",
    "Ledger webhook round-trip latency",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
WEBHOOK_FAILURES = Counter("webhook_failures_total", "Ledger webhook delivery failures")


@contextmanager
def track_request(endpoint: str):
    start = time.perf_counter()
    status = "500"
    try:
        yield lambda code: None
        status = "200"
    except Exception:
        status = "500"
        raise
    finally:
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.perf_counter() - start)
        REQUESTS.labels(method="*", endpoint=endpoint, status=status).inc()


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
