from app.errors import BusinessError
from app.merge import merge
from app.modules.m1_sessions.rules import FIELDS

BASE = "lease_id,product,user,start,end,kind,version,seats\n" \
       "00001,CAD,u1,2026-11-18T00:00:00+00:00,2026-11-18T06:00:00+00:00,online,1,1\n"


def test_merge_appends_data_rows():
    merged, info = merge(BASE, "00002,CAD,u2,2026-11-18T00:00:00+00:00,2026-11-18T06:00:00+00:00,online,1,1\n", FIELDS)
    assert merged.count("00002") == 1 and info["appended"] == 1


def test_merge_accepts_header_in_fragment():
    fragment = BASE.splitlines()[0] + "\n" + BASE.splitlines()[1].replace("00001", "00003") + "\n"
    merged, info = merge(BASE, fragment, FIELDS)
    assert merged.count("00003") == 1 and info["appended"] == 1


def test_merge_retry_is_stable():
    fragment = "00002,CAD,u2,2026-11-18T00:00:00+00:00,2026-11-18T06:00:00+00:00,online,1,1\n"
    first, _ = merge(BASE, fragment, FIELDS)
    second, info = merge(first, fragment, FIELDS)
    assert second == first and info["appended"] == 0 and info["dropped_duplicates"] == 1


def test_merge_rejects_empty():
    try:
        merge(BASE, "   \n", FIELDS)
    except BusinessError as error:
        assert error.code == "SUPPLEMENT"
    else:
        raise AssertionError("应拒绝空补传")


def test_merge_rejects_two_headers():
    header = BASE.splitlines()[0]
    try:
        merge(BASE, header + "\n" + header + "\n", FIELDS)
    except BusinessError as error:
        assert error.code == "SUPPLEMENT_HEADER"
    else:
        raise AssertionError("应拒绝重复表头")
