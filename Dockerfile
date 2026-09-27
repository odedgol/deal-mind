FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY cato_deal_intel ./cato_deal_intel
COPY synthetic_data ./synthetic_data

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

ENV CATO_FAKE_LLM=1
ENV CATO_QDRANT_PATH=/app/artifacts/qdrant

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "cato_deal_intel.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
