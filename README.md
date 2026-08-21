# Raspored časova — Ballet School Scheduler

Minimal starter project to build a constraint-based scheduler that outputs an Excel file.

Purpose
- Provide a small, maintainable codebase for two roles:
  - Developer: edits/extends Python code (solver, constraints, exports).
  - School admin (your mom): provides input data (YAML) and runs the scheduler, optionally using ChatGPT/Codex to help adjust inputs or prompts.

What's included
- src/run_scheduler.py — CLI entrypoint that reads input YAML and writes an Excel schedule.
- src/scheduler.py — Small OR-Tools CP-SAT model (simple constraints: no teacher overlap, no accompanist overlap, no student double-booking, no room overlap, room capacity).
- src/exporter.py — Exports the result to an Excel file using pandas/openpyxl.
- examples/sample_input.yaml — Minimal example of teachers, accompanists, students, rooms, classes, timeslots.
- requirements.txt — Python dependencies.
- .gitignore

Setup
1. Create and activate a Python virtual environment.
2. Install the dependencies:
   `python -m pip install -r requirements.txt`
3. Run the tests:
   `python -m pytest`

Key entities
- students: individual student IDs. Classes list which students attend.
- teacher: main teacher for a class. Must be available and can't teach two classes at once.
- accompanist: (optional) person who plays piano. Treated like a resource with availability and no double-booking.
- room: classroom/studio with capacity.

How your mom can use this (non-technical steps)
1. Fill the examples/sample_input.yaml (or copy it somewhere and edit) with the school's data: students, teachers, accompanists, rooms, classes, timeslots.
2. Run the scheduler from a terminal:
   python -m src.run_scheduler examples/sample_input.yaml output_schedule.xlsx
3. Open the produced output_schedule.xlsx in Excel.

Invalid input (such as duplicate IDs or references to missing people) produces a
clear error. The scheduler only writes an output when every class can be placed;
it never silently returns a partial schedule.

Tips for using with AI assistants
- If your mom uses ChatGPT or similar, she can paste the sample_input.yaml and ask the assistant how to modify it (e.g., add a teacher, change availability) or ask for help interpreting errors when running the script.
- Developers can ask the assistant to add new constraints (e.g., teacher max hours, multi-slot classes, grouped students) and then implement them in src/scheduler.py.

Next steps (suggested)
- Add unit tests for the solver.
- Add a small web UI or a simple form for non-technical data entry.
- Add more constraints: multi-slot lessons, teacher preferences, student grouping, fairness.

License: MIT
