#!/bin/sh
set -eu

if [ "${CATO_AUTO_INGEST:-1}" = "1" ]; then
  echo "Indexing synthetic evidence with the configured embedding provider..."
  deal-intel ingest
fi

exec python -m uvicorn cato_deal_intel.api.app:app --host 0.0.0.0 --port 8000
