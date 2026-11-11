FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

# OCR dos comprovantes (texto visível; não é IA)
RUN apt-get update  && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
