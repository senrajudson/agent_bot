from domain.pims.clients.pi_point_resolver import (
    PiPointResolution,
    ResolutionStatus,
    safe_log_payload,
)


def test_resolution_status_values():
    assert ResolutionStatus.RESOLVED == "RESOLVED"
    assert ResolutionStatus.EMPTY_RESULT == "EMPTY_RESULT"
    assert ResolutionStatus.NOT_FOUND == "NOT_FOUND"
    assert ResolutionStatus.INVALID_RESPONSE == "INVALID_RESPONSE"
    assert ResolutionStatus.TRANSPORT_ERROR == "TRANSPORT_ERROR"
    assert ResolutionStatus.AUTH_ERROR == "AUTH_ERROR"
    assert ResolutionStatus.AMBIGUOUS_RESOLUTION == "AMBIGUOUS_RESOLUTION"


def test_resolution_status_seven_values():
    assert len(ResolutionStatus) == 7


def test_pi_point_resolution_frozen():
    r = PiPointResolution(status=ResolutionStatus.RESOLVED, tag="T1")
    try:
        r.status = ResolutionStatus.NOT_FOUND
        assert False, "Should be frozen"
    except AttributeError:
        pass


def test_pi_point_resolution_is_resolved():
    resolved = PiPointResolution(status=ResolutionStatus.RESOLVED, tag="T1")
    not_found = PiPointResolution(status=ResolutionStatus.NOT_FOUND, tag="T2")
    assert resolved.is_resolved is True
    assert not_found.is_resolved is False


def test_safe_log_payload_removes_url():
    data = {"url": "http://10.247.224.39/piwebapi", "tag": "T1"}
    result = safe_log_payload(data)
    assert "url" not in result
    assert result["tag"] == "T1"


def test_safe_log_payload_removes_webid():
    data = {"WebId": "ABC123", "Name": "T1"}
    result = safe_log_payload(data)
    assert "WebId" not in result
    assert result["Name"] == "T1"


def test_safe_log_payload_removes_credential():
    data = {"Authorization": "Bearer xyz", "Password": "secret"}
    result = safe_log_payload(data)
    assert "Authorization" not in result
    assert "Password" not in result


def test_safe_log_payload_nested():
    data = {"inner": {"WebId": "ABC", "value": 42}}
    result = safe_log_payload(data)
    assert "WebId" not in result["inner"]
    assert result["inner"]["value"] == 42


def test_safe_log_payload_preserves_safe_keys():
    data = {"tag": "T1", "status": "OK", "duration_ms": 42}
    result = safe_log_payload(data)
    assert result == data
