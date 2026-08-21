import pandas as pd

from src.exporter import COLUMNS, export_to_excel


def test_exports_assignments(tmp_path):
    output = tmp_path / "schedule.xlsx"
    export_to_excel(
        [{"timeslot": "Mon-09", "students": ["S1", "S2"], "room": "R1"}],
        output,
    )

    exported = pd.read_excel(output)
    assert list(exported.columns) == COLUMNS
    assert exported.loc[0, "students"] == "S1, S2"


def test_exports_empty_schedule(tmp_path):
    output = tmp_path / "schedule.xlsx"
    export_to_excel([], output)

    assert list(pd.read_excel(output).columns) == COLUMNS
