# Airframe backend: header-only Wi-Fi diagnostics engine + Part 2/3 AI agents (FastAPI).
#
# This image is Python-only - it does NOT bundle the dashboard. The React frontend
# is its own image (see frontend/Dockerfile) and runs separately via npm; use
# ../docker-compose.yml to run both together with the frontend proxying /api to this one.
#
# This file lives in backend/, but the build context must stay the REPO ROOT (not
# backend/) because json_full/ and catalog/ are siblings of backend/ and get baked
# in below so the container is self-contained. That's why every COPY path here
# starts with "backend/" - they're resolved against the repo root, not this file's
# own directory. Build from the repo root with -f:
#
#   docker build -f backend/Dockerfile -t airframe-backend .
#   docker run --rm -p 8000:8000 -e OPENROUTER_API_KEY=$env:OPENROUTER_API_KEY airframe-backend
#
# (docker-compose.yml already sets context: . and dockerfile: backend/Dockerfile,
# so `docker compose up` from the repo root just works.)
#
# json_full/ (converted captures) and catalog/ are baked into the image; out/ is
# regenerated at runtime. If json_full/ is empty, run `python convert_full.py` on
# the host first (needs tshark + the raw pcaps in hackaton_airframe/, which are
# deliberately not shipped in the image).

FROM python:3.13-slim

# tshark powers ingest (backend/airframe/tshark.py) for pcap/live sources; the
# default demo replays pre-converted json_full/ and does not need it, but it is
# installed so --source pcap and future live-capture mode work out of the box.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends tshark \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
ENV TSHARK=/usr/bin/tshark

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY catalog/ catalog/
COPY json_full/ json_full/

RUN mkdir -p out

ENV PYTHONUNBUFFERED=1 \
    AIRFRAME_AUTOSTART=1 \
    AIRFRAME_AGENT_MODE=auto

# Agent credentials (both optional): pass at `docker run -e OPENROUTER_API_KEY=...`
# and/or `-e ANTHROPIC_API_KEY=...`. auto mode (the default) prefers OpenRouter/DeepSeek
# over Claude over the offline catalog playbook - see AGENT_MODE in config.py.
ENV OPENROUTER_API_KEY="" \
    ANTHROPIC_API_KEY="" \
    AIRFRAME_SALT="" \
    AIRFRAME_SITE_NAME="Airframe"

WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

CMD ["python", "-m", "airframe", "serve", "--host", "0.0.0.0", "--port", "8000"]
