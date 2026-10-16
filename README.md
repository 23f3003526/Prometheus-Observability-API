# Prometheus Observability API

## Deploy on Render
1. Push `main.py`, `requirements.txt`, and `render.yaml` to a GitHub repository.
2. Create a Render Web Service from that repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Endpoints
- `GET /work?n=K`: returns assigned email and requested work count.
- `GET /metrics`: live Prometheus metrics, including `http_requests_total`.
- `GET /healthz`: service status and uptime.
- `GET /logs/tail?limit=N`: recent request logs as JSON.

The middleware increments the Prometheus counter and records a structured request log for every request, including metrics, health, and log-tail requests.
