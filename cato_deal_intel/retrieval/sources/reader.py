import csv
from pathlib import Path


class TsvReader:
    """Read optional tab-separated source files from the synthetic-data root."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def read(self, relative_path: str) -> list[dict[str, str]]:
        path = self.root / relative_path
        if not path.exists():
            return []

        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))
