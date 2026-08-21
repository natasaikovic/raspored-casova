"""
Simple CP-SAT-based scheduler.
Input dict structure (see examples/sample_input.yaml):
- timeslots: ["Mon-09", "Mon-10", ...]
- rooms: [{id: "R1", capacity: 20}, ...]
- teachers: [{id: "T1", name: "Ana", available: ["Mon-09", ...]}, ...]
- accompanists: [{id: "A1", name: "Maja", available: [...]}, ...]  # optional
- students: [{id: "S1", name: "Ivana"}, ...]
- classes: [{id: "C1", name: "Ballet Beginners", teacher: "T1", students: ["S1","S2"], size: 12, accompanist: "A1"}, ...]

Output: list of assignments: [{class_id, class_name, teacher, accompanist, room, timeslot, students}]
"""
from ortools.sat.python import cp_model


def schedule_from_data(data, time_limit_seconds=10):
    timeslots = data.get('timeslots', [])
    rooms = data.get('rooms', [])
    teachers = {t['id']: t for t in data.get('teachers', [])}
    accompanists = {a['id']: a for a in data.get('accompanists', [])}
    students = {s['id']: s for s in data.get('students', [])}
    classes = data.get('classes', [])

    # Build quick lookup
    room_by_id = {r['id']: r for r in rooms}
    class_by_id = {c['id']: c for c in classes}
    room_ids = list(room_by_id.keys())

    model = cp_model.CpModel()

    # Variables: assign[(c_id, t, r)] = 0/1
    assign = {}
    for c in classes:
        c_id = c['id']
        class_size = c.get('size', len(c.get('students', [])))
        for t in timeslots:
            for r in room_ids:
                # disallow room if capacity < class size
                room = room_by_id[r]
                if room.get('capacity', 0) < class_size:
                    continue
                # disallow if teacher unavailable for timeslot
                teacher = teachers.get(c['teacher'])
                if teacher:
                    avail = teacher.get('available')
                    if avail is not None and t not in avail:
                        continue
                # disallow if accompanist specified but unavailable
                accomp_id = c.get('accompanist')
                if accomp_id:
                    accomp = accompanists.get(accomp_id)
                    if accomp:
                        avail = accomp.get('available')
                        if avail is not None and t not in avail:
                            continue
                assign[(c_id, t, r)] = model.NewBoolVar(f"assign_{c_id}_{t}_{r}")

    # Each class assigned exactly once
    for c in classes:
        c_id = c['id']
        vars_for_class = [v for (cid, tt, rr), v in assign.items() if cid == c_id]
        if not vars_for_class:
            # no feasible assignment (e.g., no room with capacity or no availability). Skip constraint to keep model consistent.
            continue
        model.Add(sum(vars_for_class) == 1)

    # No teacher overlap: for each teacher and timeslot sum <= 1
    for teacher_id in teachers.keys():
        for t in timeslots:
            vars_for_teacher_time = [v for (c_id, tt, r), v in assign.items()
                                     if tt == t and class_by_id.get(c_id, {}).get('teacher') == teacher_id]
            if vars_for_teacher_time:
                model.Add(sum(vars_for_teacher_time) <= 1)

    # No accompanist overlap: for each accompanist and timeslot sum <= 1
    for accomp_id in accompanists.keys():
        for t in timeslots:
            vars_for_accomp_time = [v for (c_id, tt, r), v in assign.items()
                                     if tt == t and class_by_id.get(c_id, {}).get('accompanist') == accomp_id]
            if vars_for_accomp_time:
                model.Add(sum(vars_for_accomp_time) <= 1)

    # No student double-booking: for each student and timeslot sum <= 1
    for student_id in students.keys():
        for t in timeslots:
            vars_for_student_time = [v for (c_id, tt, r), v in assign.items()
                                     if tt == t and student_id in class_by_id.get(c_id, {}).get('students', [])]
            if vars_for_student_time:
                model.Add(sum(vars_for_student_time) <= 1)

    # No room overlap: for each room and timeslot sum <= 1
    for r in room_ids:
        for t in timeslots:
            vars_for_room_time = [v for (c_id, tt, rr), v in assign.items() if tt == t and rr == r]
            if vars_for_room_time:
                model.Add(sum(vars_for_room_time) <= 1)

    # Optional objective: try to satisfy preferred_times if provided (soft)
    pref_literals = []
    for c in classes:
        prefs = c.get('preferred_times')
        if not prefs:
            continue
        c_id = c['id']
        for t in prefs:
            for r in room_ids:
                lit = assign.get((c_id, t, r))
                if lit is not None:
                    pref_literals.append(lit)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds

    if pref_literals:
        # maximize number of preferred assignments
        model.Maximize(sum(pref_literals))

    result = solver.Solve(model)
    if result not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return []

    assignments = []
    for (c_id, t, r), var in assign.items():
        if solver.Value(var) == 1:
            c = class_by_id.get(c_id, {})
            assignments.append({
                'class_id': c_id,
                'class_name': c.get('name'),
                'teacher': c.get('teacher'),
                'accompanist': c.get('accompanist'),
                'room': r,
                'timeslot': t,
                'students': c.get('students', []),
            })
    return assignments
