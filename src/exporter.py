"""
Export assignments (list of dicts) to Excel.
"""
import pandas as pd


def export_to_excel(assignments, output_path):
    if not assignments:
        df = pd.DataFrame([], columns=['class_id', 'class_name', 'teacher', 'accompanist', 'room', 'timeslot', 'students'])
    else:
        # flatten students list to comma-separated string for Excel
        rows = []
        for a in assignments:
            rows.append({
                'timeslot': a.get('timeslot'),
                'room': a.get('room'),
                'class_id': a.get('class_id'),
                'class_name': a.get('class_name'),
                'teacher': a.get('teacher'),
                'accompanist': a.get('accompanist'),
                'students': ", ".join(a.get('students', [])),
            })
        df = pd.DataFrame(rows)
        df = df[['timeslot', 'room', 'class_id', 'class_name', 'teacher', 'accompanist', 'students']]
    df.to_excel(output_path, index=False)
