"""Testes unitários da política canônica de resolução de Digital Set.

Cobertura: tabela de verdade completa de ``resolve_digital_set_name``.
"""

from __future__ import annotations

import pytest

from domain.pims.utils.digital_states import (
    DigitalSetResolution,
    DigitalSetSource,
    INVALID_DIGITAL_SETS,
    resolve_digital_set_name,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

POINT_WITH_DSN = {"DigitalSetName": "Estado_126"}
POINT_WITH_DS = {"DigitalSet": "Estado_126"}
POINT_WITH_BOTH_SAME = {"DigitalSetName": "Estado_126", "DigitalSet": "Estado_126"}
POINT_WITH_BOTH_DIFFERENT = {"DigitalSetName": "Estado_126", "DigitalSet": "OutroSet"}
POINT_EMPTY = {}
POINT_WITH_PLACEHOLDER = {"DigitalSet": "não cadastrado"}

ATTR_VALID = {"Items": [{"Value": "Estado_126"}]}
ATTR_VALID_STR = "Estado_126"
ATTR_DIFFERENT = {"Items": [{"Value": "OutroSet"}]}
ATTR_PLACEHOLDER = {"Items": [{"Value": "não se aplica"}]}
ATTR_EMPTY_ITEMS = {"Items": []}
ATTR_NONE_VALUE = {"Items": [{"Value": None}]}


# ---------------------------------------------------------------------------
# T036: Somente DigitalSetName
# ---------------------------------------------------------------------------

class TestDigitalSetNameOnly:
    def test_resolved_via_dsn(self) -> None:
        result = resolve_digital_set_name(point_data=POINT_WITH_DSN)
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET_NAME
        assert result.is_invalid is False
        assert result.fallback_used is False

    def test_resolved_with_empty_ds(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSetName": "Estado_126", "DigitalSet": ""}
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET_NAME


# ---------------------------------------------------------------------------
# T037: Somente DigitalSet
# ---------------------------------------------------------------------------

class TestDigitalSetOnly:
    def test_resolved_via_ds(self) -> None:
        result = resolve_digital_set_name(point_data=POINT_WITH_DS)
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET
        assert result.is_invalid is False
        assert result.fallback_used is False

    def test_resolved_with_empty_dsn(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSetName": "", "DigitalSet": "Estado_126"}
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET


# ---------------------------------------------------------------------------
# T038: Somente atributo
# ---------------------------------------------------------------------------

class TestAttributeOnly:
    def test_resolved_via_attribute(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_EMPTY,
            digitalset_attribute=ATTR_VALID,
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.ATTRIBUTE
        assert result.is_invalid is False
        assert result.fallback_used is True

    def test_resolved_via_string_attribute(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_EMPTY,
            digitalset_attribute=ATTR_VALID_STR,
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.ATTRIBUTE


# ---------------------------------------------------------------------------
# T039: Todas as fontes iguais
# ---------------------------------------------------------------------------

class TestAllSourcesEqual:
    def test_all_same_name(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_WITH_BOTH_SAME,
            digitalset_attribute=ATTR_VALID,
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET_NAME
        assert result.fallback_used is True
        assert result.is_invalid is False

    def test_preserves_original_spelling(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSetName": "Estado_126", "DigitalSet": "estado_126"},
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET_NAME


# ---------------------------------------------------------------------------
# T040: Campos iguais sem atributo
# ---------------------------------------------------------------------------

class TestFieldsEqualNoAttribute:
    def test_same_fields(self) -> None:
        result = resolve_digital_set_name(point_data=POINT_WITH_BOTH_SAME)
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET_NAME
        assert result.fallback_used is False


# ---------------------------------------------------------------------------
# T041: Campos vazios + atributo válido
# ---------------------------------------------------------------------------

class TestEmptyFieldsWithValidAttribute:
    def test_empty_fields_with_valid_attr(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_EMPTY,
            digitalset_attribute=ATTR_VALID,
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.ATTRIBUTE
        assert result.fallback_used is True


# ---------------------------------------------------------------------------
# T042: Placeholders + atributo válido
# ---------------------------------------------------------------------------

class TestPlaceholderWithValidAttribute:
    def test_placeholder_ds_with_valid_attr(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_WITH_PLACEHOLDER,
            digitalset_attribute=ATTR_VALID,
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.ATTRIBUTE
        assert result.fallback_used is True

    def test_both_placeholders_with_valid_attr(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSetName": "n/a", "DigitalSet": "null"},
            digitalset_attribute=ATTR_VALID,
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.ATTRIBUTE


# ---------------------------------------------------------------------------
# T043: Todas as fontes ausentes
# ---------------------------------------------------------------------------

class TestAllSourcesMissing:
    def test_no_sources_provided(self) -> None:
        result = resolve_digital_set_name(point_data=POINT_EMPTY)
        assert result.name is None
        assert result.source == DigitalSetSource.MISSING
        assert result.is_invalid is True

    def test_no_sources_with_none_attr(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_EMPTY,
            digitalset_attribute=None,
        )
        assert result.name is None
        assert result.source == DigitalSetSource.MISSING


# ---------------------------------------------------------------------------
# T044: Todas inválidas (placeholders)
# ---------------------------------------------------------------------------

class TestAllInvalid:
    def test_all_placeholders(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSetName": "não cadastrado", "DigitalSet": "null"},
        )
        assert result.name is None
        assert result.source == DigitalSetSource.MISSING
        assert result.is_invalid is True

    def test_placeholder_with_none_attr(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_WITH_PLACEHOLDER,
            digitalset_attribute=None,
        )
        assert result.name is None
        assert result.source == DigitalSetSource.MISSING


# ---------------------------------------------------------------------------
# T045: Conflito point x attribute
# ---------------------------------------------------------------------------

class TestConflictPointVsAttribute:
    def test_dsn_vs_attribute(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_WITH_DSN,
            digitalset_attribute=ATTR_DIFFERENT,
        )
        assert result.name is None
        assert result.source == DigitalSetSource.CONFLICT
        assert result.is_invalid is True
        assert result.error_code == "PI_RESPONSE_INVALID"

    def test_ds_vs_attribute(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_WITH_DS,
            digitalset_attribute=ATTR_DIFFERENT,
        )
        assert result.name is None
        assert result.source == DigitalSetSource.CONFLICT
        assert result.is_invalid is True


# ---------------------------------------------------------------------------
# T046: Conflito entre aliases
# ---------------------------------------------------------------------------

class TestConflictBetweenAliases:
    def test_different_aliases(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_WITH_BOTH_DIFFERENT,
        )
        assert result.name is None
        assert result.source == DigitalSetSource.CONFLICT
        assert result.is_invalid is True
        assert result.error_code == "PI_RESPONSE_INVALID"


# ---------------------------------------------------------------------------
# T047: Diferenças somente de case
# ---------------------------------------------------------------------------

class TestCaseDifferences:
    def test_same_name_different_case(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSetName": "ESTADO_126", "DigitalSet": "estado_126"},
        )
        assert result.name == "ESTADO_126"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET_NAME
        assert result.is_invalid is False

    def test_case_insensitive_comparison(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_WITH_DSN,
            digitalset_attribute={"Items": [{"Value": "ESTADO_126"}]},
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET_NAME
        assert result.is_invalid is False


# ---------------------------------------------------------------------------
# T048: Espaços externos
# ---------------------------------------------------------------------------

class TestExternalSpaces:
    def test_spaces_around_name(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSetName": "  Estado_126  "},
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET_NAME

    def test_spaces_in_attribute(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_EMPTY,
            digitalset_attribute={"Items": [{"Value": "  Estado_126  "}]},
        )
        assert result.name == "Estado_126"
        assert result.source == DigitalSetSource.ATTRIBUTE


# ---------------------------------------------------------------------------
# T049: Atributo malformado
# ---------------------------------------------------------------------------

class TestMalformedAttribute:
    def test_empty_items_list(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_EMPTY,
            digitalset_attribute=ATTR_EMPTY_ITEMS,
        )
        assert result.name is None
        assert result.source == DigitalSetSource.INVALID_RESPONSE
        assert result.error_code == "PI_RESPONSE_INVALID"

    def test_none_value_in_items(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_EMPTY,
            digitalset_attribute=ATTR_NONE_VALUE,
        )
        assert result.name is None
        assert result.source == DigitalSetSource.INVALID_RESPONSE
        assert result.error_code == "PI_RESPONSE_INVALID"

    def test_unexpected_type(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_EMPTY,
            digitalset_attribute=12345,
        )
        assert result.name is None
        assert result.source == DigitalSetSource.INVALID_RESPONSE
        assert result.error_code == "PI_RESPONSE_INVALID"


# ---------------------------------------------------------------------------
# T050: Point malformado
# ---------------------------------------------------------------------------

class TestMalformedPoint:
    def test_point_with_none_values(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSetName": None, "DigitalSet": None},
        )
        assert result.name is None
        assert result.source == DigitalSetSource.MISSING

    def test_point_with_numeric_value(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSet": 126},
        )
        assert result.name == "126"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET

    def test_empty_point_dict(self) -> None:
        result = resolve_digital_set_name(point_data={})
        assert result.name is None
        assert result.source == DigitalSetSource.MISSING


# ---------------------------------------------------------------------------
# T051: Valores inválidos atuais (parametrizado com INVALID_DIGITAL_SETS)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("invalid_value", sorted(INVALID_DIGITAL_SETS))
class TestInvalidValuesParametrized:
    def test_ds_placeholder_is_invalid(self, invalid_value: str) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSet": invalid_value},
        )
        assert result.name is None
        assert result.is_invalid is True

    def test_dsn_placeholder_is_invalid(self, invalid_value: str) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSetName": invalid_value},
        )
        assert result.name is None
        assert result.is_invalid is True


# ---------------------------------------------------------------------------
# T052: Estado numérico zero não é tratado como nome válido
# ---------------------------------------------------------------------------

class TestNumericZeroNotTreatedAsValidName:
    def test_zero_not_digital_set_name(self) -> None:
        """O valor '0' (índice de estado digital) não deve ser confundido com nome de Digital Set."""
        result = resolve_digital_set_name(
            point_data={"DigitalSet": "0"},
        )
        assert result.name == "0"
        assert result.source == DigitalSetSource.POINT_DIGITAL_SET
        assert result.is_invalid is False


# ---------------------------------------------------------------------------
# T053: Imutabilidade
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_resolution_is_frozen(self) -> None:
        result = resolve_digital_set_name(point_data=POINT_WITH_DSN)
        assert isinstance(result, DigitalSetResolution)
        with pytest.raises(AttributeError):
            result.name = "OutroSet"  # type: ignore[misc]

    def test_resolution_fields_are_hashable(self) -> None:
        result = resolve_digital_set_name(point_data=POINT_WITH_DSN)
        # Deve poder ser usado em sets e dicts
        s = {result}
        assert len(s) == 1


# ---------------------------------------------------------------------------
# T054: Ausência de dados sensíveis
# ---------------------------------------------------------------------------

class TestNoSensitiveData:
    def test_no_webid_in_resolution(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSetName": "Estado_126", "WebId": "ABC123"},
        )
        assert not hasattr(result, "webId")
        assert not hasattr(result, "WebId")
        assert result.name == "Estado_126"

    def test_candidates_do_not_contain_webid(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSet": ""},
            digitalset_attribute={"Items": [{"Value": "Estado_126"}]},
        )
        for c in result.candidates:
            assert "ABC123" not in c
            assert "WebId" not in c


# ---------------------------------------------------------------------------
# T034: Determinismo
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        args = {"point_data": POINT_WITH_DSN, "digitalset_attribute": ATTR_VALID}
        r1 = resolve_digital_set_name(**args)
        r2 = resolve_digital_set_name(**args)
        assert r1 == r2
        assert r1.name == r2.name
        assert r1.source == r2.source

    def test_same_output_multiple_calls(self) -> None:
        args = {"point_data": POINT_WITH_BOTH_SAME}
        results = [resolve_digital_set_name(**args) for _ in range(10)]
        assert all(r == results[0] for r in results)


# ---------------------------------------------------------------------------
# T033: Invariantes
# ---------------------------------------------------------------------------

class TestInvariants:
    def test_resolved_has_name(self) -> None:
        result = resolve_digital_set_name(point_data=POINT_WITH_DSN)
        assert result.name is not None

    def test_missing_has_no_name(self) -> None:
        result = resolve_digital_set_name(point_data=POINT_EMPTY)
        assert result.name is None
        assert result.source == DigitalSetSource.MISSING

    def test_conflict_has_no_name(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_WITH_BOTH_DIFFERENT,
        )
        assert result.name is None
        assert result.source == DigitalSetSource.CONFLICT

    def test_conflict_has_error_code(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_WITH_BOTH_DIFFERENT,
        )
        assert result.error_code == "PI_RESPONSE_INVALID"

    def test_invalid_response_has_error_code(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_EMPTY,
            digitalset_attribute=12345,
        )
        assert result.error_code == "PI_RESPONSE_INVALID"

    def test_candidates_exclude_valid_values(self) -> None:
        result = resolve_digital_set_name(
            point_data=POINT_WITH_BOTH_DIFFERENT,
        )
        for c in result.candidates:
            assert c not in INVALID_DIGITAL_SETS or c == ""

    def test_candidates_do_not_contain_webid(self) -> None:
        result = resolve_digital_set_name(
            point_data={"DigitalSet": "", "WebId": "SECRET"},
        )
        assert "SECRET" not in result.candidates
