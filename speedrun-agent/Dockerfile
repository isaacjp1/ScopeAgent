# v41: slim image (~0.7 GB): Python + Playwright + Chromium headless shell only.
FROM python:3.12-slim
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir playwright==1.56.0 pypdf==5.1.0 tzdata==2025.2 && playwright install --with-deps --only-shell chromium && rm -rf /var/lib/apt/lists/* /root/.cache
WORKDIR /app
COPY agent ./agent
# Knobs (see agent/config.py for all of them). Leave MODEL empty to pick from MODEL_PREFS.
ENV PAGE_POOL=6
ENV EXPLORE_SECONDS=22
ENV REPLAY_MAX=16
ENV MIN_CONFIDENCE=0.6
ENV GATE=1
CMD ["python3", "-m", "agent.main"]
