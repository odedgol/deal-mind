FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY cato_deal_intel ./cato_deal_intel
COPY synthetic_data ./synthetic_data
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN pip install --no-cache-dir .
RUN chmod +x /app/docker-entrypoint.sh

ENV CATO_QDRANT_PATH=/app/artifacts/qdrant

EXPOSE 8000

CMD ["/app/docker-entrypoint.sh"]
