FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.6.10 /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Copy source
COPY src/ src/

ENV PYTHONPATH=/app/src

CMD ["uv", "run", "--no-sync", "uvicorn", "mtg_helper.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
