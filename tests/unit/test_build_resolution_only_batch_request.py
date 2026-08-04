from domain.pims.clients.pi_web_api_client import (
    POINT_SELECTED_FIELDS,
    build_resolution_only_batch_request,
)


def test_has_single_point_key():
    batch = build_resolution_only_batch_request("LFS_RB2_AC_MA_VIB_VEL")
    assert "point_0" in batch
    assert len(batch) == 1


def test_method_is_get():
    batch = build_resolution_only_batch_request("T1")
    assert batch["point_0"]["Method"] == "GET"


def test_resource_contains_path():
    batch = build_resolution_only_batch_request("LFS_RB2_AC_MA_VIB_VEL")
    resource = batch["point_0"]["Resource"]
    assert "path=" in resource
    assert "LFS_RB2_AC_MA_VIB_VEL" in resource


def test_resource_contains_selected_fields():
    batch = build_resolution_only_batch_request("T1")
    resource = batch["point_0"]["Resource"]
    assert f"selectedFields={POINT_SELECTED_FIELDS}" in resource


def test_resource_contains_pi_server_name():
    batch = build_resolution_only_batch_request("T1")
    resource = batch["point_0"]["Resource"]
    assert "PIMS" in resource or "pims" in resource.lower()


def test_no_value_or_attribute_keys():
    batch = build_resolution_only_batch_request("T1")
    assert "value_0" not in batch
    assert "instrumenttag_0" not in batch
    assert "engunits_0" not in batch
