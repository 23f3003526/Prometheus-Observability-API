import json
import logging
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware

EMAIL = "23f3003526@ds.study.iitm.ac.in"
START_TIME = time.monotonic()

# A single process-local Prometheus counter, incremented by middleware for every request.
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total number of HTTP requests received by the application",
)

LOG_LIMIT = 500
log_entries = deque(maxlen=LOG_LIMIT)
log_lock = Lock()


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "level": record.levelname.lower(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "path": getattr(record, "path", ""),
            "request_id": getattr(record, "request_id", ""),
            "method": getattr(record, "method", ""),
            "status_code": getattr(record, "status_code", None),
            "message": record.getMessage(),
        }
        return json.dumps(data, separators=(",", ":"))


logger = logging.getLogger("observability_api")
logger.setLevel(logging.INFO)
logger.propagate = False
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(JsonFormatter())
logger.addHandler(stream_handler)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        path = request.url.path
        HTTP_REQUESTS.inc()
        status_code = 500
        started = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "path": path,
                    "request_id": request_id,
                    "method": request.method,
                    "status_code": 500,
                },
            )
            raise
        finally:
            entry = {
                "level": "info" if status_code < 500 else "error",
                "ts": datetime.now(timezone.utc).isoformat(),
                "path": path,
                "request_id": request_id,
                "method": request.method,
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            }
            with log_lock:
                log_entries.append(entry)
            logger.info(
                "http_request",
                extra={
                    "path": path,
                    "request_id": request_id,
                    "method": request.method,
                    "status_code": status_code,
                },
            )


app = FastAPI(title="Prometheus Observability API")
app.add_middleware(ObservabilityMiddleware)


@app.get("/work")
async def work(n: int = 1):
    # Keep work bounded while preserving the requested done count.
    done = max(0, n)
    accumulator = 0
    for i in range(min(done, 100_000)):
        accumulator += i
    return {"email": EMAIL, "done": done}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "uptime_s": float(max(0.0, time.monotonic() - START_TIME))}


@app.get("/logs/tail")
async def logs_tail(limit: int = 100):
    limit = max(0, min(limit, LOG_LIMIT))
    with log_lock:
        entries = list(log_entries)[-limit:] if limit else []
    return entries
