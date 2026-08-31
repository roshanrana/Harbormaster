# uv-based build. The dependency layer is installed from the lockfile before
# source is copied, so editing a parser does not reinstall polars.
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY python/pyproject.toml python/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY python/src ./src
RUN uv sync --frozen --no-dev

ARG ENTRYPOINT_MODULE=inspector.main
ENV HM_ENTRYPOINT_MODULE=${ENTRYPOINT_MODULE} \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src

RUN useradd -u 10001 -m hm && chown -R hm /app
USER hm

# Shell form so HM_ENTRYPOINT_MODULE expands at runtime, letting inspector and
# reconstub share this image.
ENTRYPOINT ["sh", "-c", "exec python -m ${HM_ENTRYPOINT_MODULE}"]
