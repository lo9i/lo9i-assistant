FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Tools available to the agent's bash tool.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git jq less procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" WORKSPACE_DIR=/workspace
RUN mkdir -p /workspace
CMD ["assistant"]
