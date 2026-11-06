FROM nvidia/cuda:13.2.1-cudnn-runtime-ubuntu24.04@sha256:1c0c68dbf3258d32b446a02cb4be05c8478b65d320d7856ad33c4bbdf898ca86

COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /uvx /bin/

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FEDSIM_DATA_DIR=/var/lib/fedsim \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv python install && uv sync --locked --extra gpu --no-install-project --no-editable

COPY README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --extra gpu --no-editable

EXPOSE 8000
CMD ["uvicorn", "fedsim.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
