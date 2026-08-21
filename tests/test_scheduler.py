import copy

import pytest
import yaml

from src.scheduler import SchedulingError, schedule_from_data


@pytest.fixture
def sample_data():
    with open("examples/sample_input.yaml", encoding="utf-8") as input_file:
        return yaml.safe_load(input_file)


def test_sample_produces_complete_conflict_free_schedule(sample_data):
    schedule = schedule_from_data(sample_data)

    assert {item["class_id"] for item in schedule} == {
        item["id"] for item in sample_data["classes"]
    }
    assert len({(item["room"], item["timeslot"]) for item in schedule}) == len(schedule)


def test_rejects_unknown_resource_reference(sample_data):
    sample_data["classes"][0]["teacher"] = "missing"

    with pytest.raises(ValueError, match="unknown teacher"):
        schedule_from_data(sample_data)


def test_rejects_duplicate_ids(sample_data):
    sample_data["rooms"].append(copy.deepcopy(sample_data["rooms"][0]))

    with pytest.raises(ValueError, match="Duplicate room id"):
        schedule_from_data(sample_data)


def test_raises_when_a_class_has_no_feasible_assignment(sample_data):
    sample_data["classes"][0]["size"] = 100

    with pytest.raises(SchedulingError, match="no feasible room and timeslot"):
        schedule_from_data(sample_data)


def test_raises_instead_of_returning_partial_schedule(sample_data):
    sample_data["timeslots"] = ["Mon-09"]
    for teacher in sample_data["teachers"]:
        teacher["available"] = ["Mon-09"]

    with pytest.raises(SchedulingError, match="No complete schedule"):
        schedule_from_data(sample_data)
