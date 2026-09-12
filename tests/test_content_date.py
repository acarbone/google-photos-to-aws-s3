"""content_date.py: embedded-in-bytes capture-date extraction. Every
fixture here is hand-crafted (no image/video library dependency for
tests) so exact byte structures — including the edge cases risk-analyst
flagged (64-bit box sizes, mvhd version 1, creation_time == 0, a
placeholder EXIF date) — are precisely controlled.
"""

from __future__ import annotations

import datetime
import io
import struct

from gphotos2s3 import content_date

_QT_EPOCH = datetime.datetime(1904, 1, 1)


# --------------------------------------------------------------------------
# EXIF (JPEG) fixtures
# --------------------------------------------------------------------------


def _build_jpeg_with_ifd0_datetime(date_str: bytes) -> bytes:
    """Minimal JPEG: SOI + APP1(Exif, one IFD0 entry: DateTime 0x0132) + EOI."""
    tiff_header = b"II" + struct.pack("<H", 42) + struct.pack("<I", 8)
    num_entries = 1
    tag, typ, count = 0x0132, 2, len(date_str)
    value_offset_pos = 8 + 2 + 12 * num_entries + 4
    entry = struct.pack("<HHI", tag, typ, count) + struct.pack("<I", value_offset_pos)
    next_ifd = struct.pack("<I", 0)
    tiff = tiff_header + struct.pack("<H", num_entries) + entry + next_ifd + date_str
    app1_body = b"Exif\x00\x00" + tiff
    app1 = b"\xff\xe1" + struct.pack(">H", len(app1_body) + 2) + app1_body
    return b"\xff\xd8" + app1 + b"\xff\xd9"


def test_extract_exif_date_from_jpeg():
    jpeg = _build_jpeg_with_ifd0_datetime(b"2020:05:01 14:30:22\x00")
    result = content_date.extract_taken_at(io.BytesIO(jpeg), ".jpg")
    assert result == datetime.datetime(2020, 5, 1, 14, 30, 22)


def test_exif_placeholder_zero_date_returns_none_not_raises():
    """'0000:00:00 00:00:00' is a common real-world placeholder (unset
    camera clock) — must resolve to None, never propagate a ValueError
    (risk-analyst High finding: an uncaught exception here would
    misclassify as a systemic failure and halt the whole run)."""
    jpeg = _build_jpeg_with_ifd0_datetime(b"0000:00:00 00:00:00\x00")
    assert content_date.extract_taken_at(io.BytesIO(jpeg), ".jpg") is None


def test_unsupported_format_returns_none():
    assert content_date.extract_taken_at(io.BytesIO(b"GIF89a...."), ".gif") is None
    assert content_date.extract_taken_at(io.BytesIO(b"\x89PNG\r\n\x1a\n"), ".png") is None


def test_garbage_and_empty_bytes_return_none_never_raise():
    assert content_date.extract_taken_at(io.BytesIO(b"not a jpeg at all"), ".jpg") is None
    assert content_date.extract_taken_at(io.BytesIO(b""), ".jpg") is None
    assert content_date.extract_taken_at(io.BytesIO(b"\x00" * 3), ".mp4") is None


# --------------------------------------------------------------------------
# ISO-BMFF (`mvhd`) fixtures
# --------------------------------------------------------------------------


def _box(box_type: bytes, body: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(body), box_type) + body


def _box_largesize(box_type: bytes, body: bytes) -> bytes:
    """size field == 1 -> real size follows as an 8-byte largesize."""
    total = 16 + len(body)
    return struct.pack(">I4sQ", 1, box_type, total) + body


def _mvhd_body_v0(creation_time: int) -> bytes:
    return (
        struct.pack(">I", 0)  # version(1) + flags(3), version=0
        + struct.pack(">I", creation_time)
        + struct.pack(">I", 0)  # modification_time
        + struct.pack(">I", 600)  # timescale
        + struct.pack(">I", 0)  # duration
    )


def _mvhd_body_v1(creation_time: int) -> bytes:
    return (
        bytes([1, 0, 0, 0])  # version=1, flags=0
        + struct.pack(">Q", creation_time)  # 64-bit creation_time
        + struct.pack(">Q", 0)  # 64-bit modification_time
        + struct.pack(">I", 600)  # timescale
        + struct.pack(">Q", 0)  # 64-bit duration
    )


class _CountingBytesIO(io.BytesIO):
    """Records every requested read size, to prove the mvhd walker never
    attempts to read a box body it only needs to skip over."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.read_sizes: list[int | None] = []

    def read(self, size: int | None = -1) -> bytes:  # type: ignore[override]
        self.read_sizes.append(size)
        return super().read(size)


def test_extract_mvhd_date_version0():
    target = datetime.datetime(2021, 6, 15, 10, 0, 0)
    creation_time = int((target - _QT_EPOCH).total_seconds())
    mvhd = _box(b"mvhd", _mvhd_body_v0(creation_time))
    ftyp = _box(b"ftyp", b"isom" + b"\x00" * 8)
    mp4 = ftyp + _box(b"moov", mvhd)
    assert content_date.extract_taken_at(io.BytesIO(mp4), ".mp4") == target


def test_extract_mvhd_date_version1_64bit_creation_time():
    target = datetime.datetime(2018, 3, 3, 8, 15, 0)
    creation_time = int((target - _QT_EPOCH).total_seconds())
    mvhd = _box(b"mvhd", _mvhd_body_v1(creation_time))
    mp4 = _box(b"moov", mvhd)
    assert content_date.extract_taken_at(io.BytesIO(mp4), ".mov") == target


def test_mvhd_creation_time_zero_means_not_set():
    mvhd = _box(b"mvhd", _mvhd_body_v0(0))
    mp4 = _box(b"moov", mvhd)
    assert content_date.extract_taken_at(io.BytesIO(mp4), ".mp4") is None


def test_top_level_box_with_64bit_largesize_header_is_skipped_correctly():
    target = datetime.datetime(2019, 12, 25, 9, 0, 0)
    creation_time = int((target - _QT_EPOCH).total_seconds())
    mvhd = _box(b"mvhd", _mvhd_body_v0(creation_time))
    ftyp = _box_largesize(b"ftyp", b"isom" + b"\x00" * 8)
    mp4 = ftyp + _box(b"moov", mvhd)
    assert content_date.extract_taken_at(io.BytesIO(mp4), ".mp4") == target


def test_mvhd_walker_never_reads_mdat_body_only_seeks_past_it():
    """`moov` placed after a large `mdat` (the real-world case this design
    exists to handle cheaply) — the walker must skip mdat's body via seek,
    never a bulk read (risk-analyst High finding: reading the whole file
    just for a timestamp would be expensive on a multi-GB video)."""
    target = datetime.datetime(2022, 7, 4, 12, 0, 0)
    creation_time = int((target - _QT_EPOCH).total_seconds())
    mvhd = _box(b"mvhd", _mvhd_body_v0(creation_time))
    ftyp = _box(b"ftyp", b"isom" + b"\x00" * 8)
    mdat = _box(b"mdat", b"\x00" * 2_000_000)  # stand-in for a large media payload
    mp4 = ftyp + mdat + _box(b"moov", mvhd)

    f = _CountingBytesIO(mp4)
    result = content_date.extract_taken_at(f, ".mp4")
    assert result == target
    # Every read the walker issues is a small, fixed-size header/field read
    # (8 or 16-byte box headers, 4/8-byte mvhd fields) — never anything
    # approaching mdat's ~2MB declared body.
    assert all(size is not None and size <= 16 for size in f.read_sizes)


def test_moov_unreachable_returns_none_without_hanging():
    """A box declaring a largesize that extends past EOF, with no `moov`
    ever reachable, must resolve to None rather than looping or raising."""
    huge_declared_end = 16 + 5_000_000_000
    header = struct.pack(">I4sQ", 1, b"mdat", huge_declared_end)
    mp4 = _box(b"ftyp", b"isom" + b"\x00" * 8) + header  # no real bytes for the huge body
    assert content_date.extract_taken_at(io.BytesIO(mp4), ".mp4") is None


def test_moov_with_no_mvhd_child_returns_none():
    mp4 = _box(b"moov", _box(b"udta", b"not mvhd"))
    assert content_date.extract_taken_at(io.BytesIO(mp4), ".mp4") is None
