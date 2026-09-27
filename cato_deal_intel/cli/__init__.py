"""Command-line interface for local use and evaluation."""

from .app import ARTIFACTS_ROOT, DEAL_REPOSITORY, RUN_ARTIFACT_SERVICE, SOURCE_DATA_ROOT, app

__all__ = [
    "ARTIFACTS_ROOT",
    "DEAL_REPOSITORY",
    "RUN_ARTIFACT_SERVICE",
    "SOURCE_DATA_ROOT",
    "app",
]
