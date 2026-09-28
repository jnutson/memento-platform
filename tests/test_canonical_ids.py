import hashlib

import pytest

from memento.canonical import stable_id


def test_identifier_preimage_and_prefix():
    expected = hashlib.sha256(b"memento|v1|location|walmart|0|10").hexdigest()
    assert stable_id("location", 0, 10) == "loc_" + expected
    assert stable_id("product", 0, 100).startswith("prd_")
    assert len(stable_id("product", 0, 100)) == 68


@pytest.mark.parametrize("value", [-1, True, "1"])
def test_identifier_rejects_noncanonical_components(value):
    with pytest.raises(ValueError):
        stable_id("location", 0, value)
