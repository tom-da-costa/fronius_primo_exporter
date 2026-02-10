FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY *.py ./

ENV UV_NO_SYNC=1

ENTRYPOINT ["uv", "run", "main.py"]
