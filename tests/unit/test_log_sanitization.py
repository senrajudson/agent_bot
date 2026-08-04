from domain.pims.clients.pi_point_resolver import safe_log_payload


def test_removes_url():
    data = {"url": "http://10.247.224.39/piwebapi", "tag": "T1"}
    result = safe_log_payload(data)
    assert "url" not in result
    assert result["tag"] == "T1"


def test_removes_ip():
    data = {"IP": "10.247.224.39", "tag": "T1"}
    result = safe_log_payload(data)
    assert "IP" not in result


def test_removes_webid():
    data = {"WebId": "ABC123", "Name": "T1"}
    result = safe_log_payload(data)
    assert "WebId" not in result


def test_removes_credential():
    data = {"Authorization": "Bearer xyz", "Password": "secret"}
    result = safe_log_payload(data)
    assert "Authorization" not in result
    assert "Password" not in result


def test_nested_sanitization():
    data = {"inner": {"WebId": "ABC", "value": 42}}
    result = safe_log_payload(data)
    assert "WebId" not in result["inner"]
    assert result["inner"]["value"] == 42


def test_preserves_safe_keys():
    data = {"tag": "T1", "status": "OK", "duration_ms": 42}
    result = safe_log_payload(data)
    assert result == data
