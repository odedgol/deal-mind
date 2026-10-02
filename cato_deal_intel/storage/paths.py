"""Central locations for source data and local runtime artifacts."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SOURCE_DATA_PATH = Path("synthetic_data")
RUN_ARTIFACTS_PATH = Path("artifacts/runs")
QDRANT_PATH = Path(os.getenv("CATO_QDRANT_PATH", "artifacts/qdrant"))
