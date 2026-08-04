from domain.pims.utils.pi_response_formatter import (
    extract_unresolved_subresponse_indices,
)


def test_all_ok():
    raw = {
        "point_0": {"Status": 200, "Content": {"Name": "T1"}},
        "point_1": {"Status": 200, "Content": {"Name": "T2"}},
    }
    result = extract_unresolved_subresponse_indices(raw, 2)
    assert result == []


def test_one_failure():
    raw = {
        "point_0": {"Status": 200, "Content": {"Name": "T1"}},
        "point_1": {"Status": 404, "Content": {}},
    }
    result = extract_unresolved_subresponse_indices(raw, 2)
    assert result == [1]


def test_multiple_failures():
    raw = {
        "point_0": {"Status": 500, "Content": {}},
        "point_1": {"Status": 200, "Content": {"Name": "T2"}},
        "point_2": {"Status": 404, "Content": {}},
    }
    result = extract_unresolved_subresponse_indices(raw, 3)
    assert result == [0, 2]


def test_empty_batch():
    raw = {}
    result = extract_unresolved_subresponse_indices(raw, 0)
    assert result == []


def test_missing_point_entry():
    raw = {"point_0": {"Status": 200, "Content": {"Name": "T1"}}}
    result = extract_unresolved_subresponse_indices(raw, 3)
    assert result == [1, 2]


def test_status_zero_treated_as_unresolved():
    raw = {"point_0": {"Status": 0, "Content": {}}}
    result = extract_unresolved_subresponse_indices(raw, 1)
    assert result == [0]
