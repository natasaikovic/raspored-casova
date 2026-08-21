"""Build a conflict-free schedule from validated input data."""

from collections import defaultdict
from typing import Any

from ortools.sat.python import cp_model


class SchedulingError(RuntimeError):
    """Raised when valid input has no complete schedule."""


def _index(items: list[dict[str, Any]], kind: str) -> dict[str, dict[str, Any]]:
    """Index entities by ID while checking the common input rules."""
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = item.get("id")
        if not item_id:
            raise ValueError(f"Every {kind} must have an id")
        if item_id in indexed:
            raise ValueError(f"Duplicate {kind} id: {item_id}")
        indexed[item_id] = item
    return indexed


def _validate(data: dict[str, Any]) -> tuple[
    list[str],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    timeslots = data.get("timeslots", [])
    if not timeslots:
        raise ValueError("At least one timeslot is required")
    if len(timeslots) != len(set(timeslots)):
        raise ValueError("Timeslot names must be unique")

    rooms = _index(data.get("rooms", []), "room")
    teachers = _index(data.get("teachers", []), "teacher")
    accompanists = _index(data.get("accompanists", []), "accompanist")
    students = _index(data.get("students", []), "student")
    classes = _index(data.get("classes", []), "class")
    if not rooms:
        raise ValueError("At least one room is required")

    for room_id, room in rooms.items():
        if not isinstance(room.get("capacity"), int) or room["capacity"] < 0:
            raise ValueError(f"Room {room_id} must have a non-negative integer capacity")

    for class_id, lesson in classes.items():
        teacher_id = lesson.get("teacher")
        if teacher_id not in teachers:
            raise ValueError(f"Class {class_id} references unknown teacher: {teacher_id}")
        accompanist_id = lesson.get("accompanist")
        if accompanist_id is not None and accompanist_id not in accompanists:
            raise ValueError(
                f"Class {class_id} references unknown accompanist: {accompanist_id}"
            )
        unknown_students = set(lesson.get("students", [])) - students.keys()
        if unknown_students:
            names = ", ".join(sorted(unknown_students))
            raise ValueError(f"Class {class_id} references unknown students: {names}")
        size = lesson.get("size", len(lesson.get("students", [])))
        if not isinstance(size, int) or size < 0:
            raise ValueError(f"Class {class_id} must have a non-negative integer size")

    return timeslots, rooms, teachers, accompanists, students, classes


def schedule_from_data(
    data: dict[str, Any], time_limit_seconds: float = 10
) -> list[dict[str, Any]]:
    """Return a complete schedule or raise when the input cannot be scheduled."""
    timeslots, rooms, teachers, accompanists, students, classes = _validate(data)
    model = cp_model.CpModel()
    assignments: dict[tuple[str, str, str], Any] = {}
    by_class: dict[str, list[Any]] = defaultdict(list)
    by_teacher_time: dict[tuple[str, str], list[Any]] = defaultdict(list)
    by_accompanist_time: dict[tuple[str, str], list[Any]] = defaultdict(list)
    by_student_time: dict[tuple[str, str], list[Any]] = defaultdict(list)
    by_room_time: dict[tuple[str, str], list[Any]] = defaultdict(list)

    for class_id, lesson in classes.items():
        size = lesson.get("size", len(lesson.get("students", [])))
        teacher_id = lesson["teacher"]
        accompanist_id = lesson.get("accompanist")
        teacher_availability = teachers[teacher_id].get("available")
        accompanist_availability = (
            accompanists[accompanist_id].get("available") if accompanist_id else None
        )

        for timeslot in timeslots:
            if teacher_availability is not None and timeslot not in teacher_availability:
                continue
            if (
                accompanist_availability is not None
                and timeslot not in accompanist_availability
            ):
                continue
            for room_id, room in rooms.items():
                if room["capacity"] < size:
                    continue
                variable = model.NewBoolVar(f"assign_{class_id}_{timeslot}_{room_id}")
                assignments[class_id, timeslot, room_id] = variable
                by_class[class_id].append(variable)
                by_teacher_time[teacher_id, timeslot].append(variable)
                by_room_time[room_id, timeslot].append(variable)
                if accompanist_id:
                    by_accompanist_time[accompanist_id, timeslot].append(variable)
                for student_id in lesson.get("students", []):
                    by_student_time[student_id, timeslot].append(variable)

    for class_id in classes:
        if not by_class[class_id]:
            raise SchedulingError(f"Class {class_id} has no feasible room and timeslot")
        model.AddExactlyOne(by_class[class_id])
    for grouped_variables in (
        by_teacher_time,
        by_accompanist_time,
        by_student_time,
        by_room_time,
    ):
        for variables in grouped_variables.values():
            model.AddAtMostOne(variables)

    preferred = [
        variable
        for (class_id, timeslot, _), variable in assignments.items()
        if timeslot in classes[class_id].get("preferred_times", [])
    ]
    if preferred:
        model.Maximize(sum(preferred))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SchedulingError("No complete schedule satisfies all constraints")

    return [
        {
            "class_id": class_id,
            "class_name": classes[class_id].get("name"),
            "teacher": classes[class_id]["teacher"],
            "accompanist": classes[class_id].get("accompanist"),
            "room": room_id,
            "timeslot": timeslot,
            "students": classes[class_id].get("students", []),
        }
        for (class_id, timeslot, room_id), variable in assignments.items()
        if solver.Value(variable)
    ]
