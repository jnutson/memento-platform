import pytest

from memento.walmart import map_retail_type


@pytest.mark.parametrize(("source", "canonical"), [(0, "regular"), (7, "rollback"), (8, "clearance")])
def test_retail_type_mapping_is_pinned(source, canonical):
    assert map_retail_type(source) == canonical


def test_unknown_retail_type_is_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        map_retail_type(1)
