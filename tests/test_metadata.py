from __future__ import annotations

import datetime

from gphotos2s3.metadata import parse_sidecar
from tests.conftest import make_sidecar


def test_parses_full_sidecar():
    result = parse_sidecar(make_sidecar())
    assert result["latitude"] == 45.0
    assert result["longitude"] == 9.0
    assert result["description"] == "A test photo"
    assert result["favorited"] is True
    assert result["people"] == ["Alice"]


def test_tolerant_of_missing_keys():
    result = parse_sidecar(b"{}")
    assert result == {}


def test_tolerant_of_extra_unknown_keys():
    result = parse_sidecar(b'{"someUnknownField": 42, "description": "hi"}')
    assert result["description"] == "hi"
    assert "someUnknownField" not in result


def test_tolerant_of_non_dict_json():
    assert parse_sidecar(b"[1, 2, 3]") == {}


def test_taken_at_value_correctness_epoch_seconds_utc():
    # 1700000000 == 2023-11-14T22:13:20Z
    result = parse_sidecar(make_sidecar(taken_at_epoch=1700000000))
    expected = datetime.datetime.fromtimestamp(1700000000, tz=datetime.timezone.utc)
    parsed = datetime.datetime.fromisoformat(result["taken_at"])
    assert parsed == expected
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == datetime.timedelta(0)


def test_missing_geo_data_zero_coordinates_excluded():
    result = parse_sidecar(b'{"geoData": {"latitude": 0.0, "longitude": 0.0}}')
    assert "latitude" not in result
    assert "longitude" not in result


def test_favorited_false_is_preserved():
    result = parse_sidecar(make_sidecar(favorited=False))
    assert result["favorited"] is False
