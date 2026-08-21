"""Export schedule assignments to Excel."""

from pathlib import Path
from typing import Any

import pandas as pd


COLUMNS = [
    "timeslot",
    "room",
    "class_id",
    "class_name",
    "teacher",
    "accompanist",
    "students",
]


def export_to_excel(assignments: list[dict[str, Any]], output_path: str | Path) -> None:
    """Write assignments to an Excel workbook with a stable column order."""
    rows = [
        assignment | {"students": ", ".join(assignment.get("students", []))}
        for assignment in assignments
    ]
    pd.DataFrame(rows, columns=COLUMNS).to_excel(output_path, index=False)
