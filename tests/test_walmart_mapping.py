import pytest

from memento.walmart import SOURCE_TYPES, is_valid_iana_timezone, map_retail_type


@pytest.mark.parametrize(("source", "canonical"), [(0, "regular"), (7, "rollback"), (8, "clearance")])
def test_retail_type_mapping_is_pinned(source, canonical):
    assert map_retail_type(source) == canonical


def test_unknown_retail_type_is_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        map_retail_type(1)


def test_psp_integer_widths_are_pinned():
    assert SOURCE_TYPES["calendar_dim"][2:4] == ["TINYINT", "TINYINT"]
    assert SOURCE_TYPES["store_dim"][2] == "TINYINT"
    assert SOURCE_TYPES["omni_item_dimensions"][6] == "SMALLINT"
    assert SOURCE_TYPES["store_sales"][2] == "TINYINT"
    assert SOURCE_TYPES["long_rng_store_dmd_frcst"][2] == "TINYINT"


@pytest.mark.parametrize(
    ("name", "valid"),
    [
        ("America/Los_Angeles", True),
        ("America/New_York", True),
        ("Not/A_Timezone", False),
        ("posixrules", False),
        ("../etc/passwd", False),
        ("", False),
        (None, False),
    ],
)
def test_iana_timezone_validation(name, valid):
    assert is_valid_iana_timezone(name) is valid
