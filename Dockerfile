FROM python:3.11-slim

WORKDIR /app

# Install deps first for better layer caching
COPY pyproject.toml README.md ./
COPY bitarena ./bitarena
RUN pip install --no-cache-dir -e ".[api,mcp,llm]"

# UI + the real signed evidence the API serves (leaderboard / ledgers / debate)
COPY web ./web
COPY evidence/last_run ./evidence/last_run
COPY evidence/llm_debate.json ./evidence/llm_debate.json

ENV PORT=8000
EXPOSE 8000

# Honors $PORT (Render/Fly/Railway set it). The firewall uses ARENA_SIGNING_KEY_B64
# if provided, otherwise generates an ephemeral key on boot.
CMD ["sh", "-c", "uvicorn bitarena.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
