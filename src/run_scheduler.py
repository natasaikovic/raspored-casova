"""Command-line entry point for the scheduler."""

import argparse
from pathlib import Path

import yaml

from .exporter import export_to_excel
from .scheduler import SchedulingError, schedule_from_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a ballet school schedule")
    parser.add_argument("input", type=Path, help="YAML input file")
    parser.add_argument("output", type=Path, help="Excel output file")
    args = parser.parse_args()

    with args.input.open(encoding="utf-8") as input_file:
        data = yaml.safe_load(input_file) or {}

    try:
        assignments = schedule_from_data(data)
    except (ValueError, SchedulingError) as error:
        parser.error(str(error))
    export_to_excel(assignments, args.output)
    print(f"Scheduled {len(assignments)} classes in {args.output}")


if __name__ == "__main__":
    main()
