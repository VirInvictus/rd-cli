from __future__ import annotations

import pytest

from conftest import FakeOpener, http_error
from rd_cli.errors import APIError, AuthError, RateLimitError
from rd_cli.pinboard import PinboardClient


def make_client(responses, *, min_interval=0.0, **kwargs):
    """A PinboardClient over a FakeOpener. ``min_interval`` defaults to 0 so
    tests do not pace; the pacing path is exercised explicitly below."""
    calls: list[float] = []
    opener = FakeOpener(responses)
    c = PinboardClient(
        "user:TOK",
        opener=opener,
        sleep=calls.append,
        min_interval=min_interval,
        **kwargs,
    )
    return c, opener, calls


# -- request construction -----------------------------------------------------


def test_auth_token_and_json_format_in_query():
    c, opener, _ = make_client([{"update_time": "2026-01-01T00:00:00Z"}])
    c.last_update()
    url = opener.last.full_url
    assert "auth_token=" in url
    assert "format=json" in url
    assert opener.last.get_method() == "GET"


def test_get_all_returns_bare_list():
    c, _, _ = make_client([[{"href": "https://a"}, {"href": "https://b"}]])
    posts = c.get_all()
    assert [p["href"] for p in posts] == ["https://a", "https://b"]


def test_get_post_returns_none_when_absent():
    c, _, _ = make_client([{"posts": []}])
    assert c.get_post("https://nope") is None


def test_add_post_maps_flags_and_joins_tags():
    c, opener, _ = make_client([{"result_code": "done"}])
    c.add_post(
        "https://x",
        "Title",
        tags=["a", "b"],
        shared=False,
        toread=True,
        replace=True,
    )
    url = opener.last.full_url
    assert "tags=a+b" in url or "tags=a%20b" in url
    assert "shared=no" in url
    assert "toread=yes" in url
    assert "replace=yes" in url


def test_check_raises_on_non_done_result():
    c, _, _ = make_client([{"result_code": "item already exists"}])
    with pytest.raises(APIError) as ei:
        c.add_post("https://x", "T")
    assert "already exists" in str(ei.value)


def test_get_tags_coerces_counts_to_int():
    c, _, _ = make_client([{"cooking": "47", "chef": "35"}])
    assert c.get_tags() == {"cooking": 47, "chef": 35}


def test_suggest_flattens_popular_and_recommended():
    c, _, _ = make_client(
        [[{"popular": ["food"]}, {"recommended": ["chef", "recipe"]}]]
    )
    out = c.suggest_tags("https://x")
    assert out == {"popular": ["food"], "recommended": ["chef", "recipe"]}


# -- edit is read-modify-write (Pinboard has no PUT) --------------------------


def test_edit_post_preserves_untouched_fields():
    # get -> current state; add -> the re-save. Only the title changes here, so
    # the existing tags/shared/toread must be carried through unchanged.
    current = {
        "posts": [
            {"description": "old", "tags": "x y", "shared": "no", "toread": "yes"}
        ]
    }
    c, opener, _ = make_client([current, {"result_code": "done"}])
    c.edit_post("https://x", title="new")
    saved = opener.last.full_url
    assert "description=new" in saved
    assert "tags=x+y" in saved or "tags=x%20y" in saved
    assert "shared=no" in saved
    assert "toread=yes" in saved


def test_edit_post_missing_raises():
    c, _, _ = make_client([{"posts": []}])
    with pytest.raises(APIError):
        c.edit_post("https://gone", title="new")


# -- pacing and retry ---------------------------------------------------------


def test_pacing_sleeps_between_calls():
    # Clock reads, in order: (1) first call stamps _last_call = 0.0; (2) second
    # call's _pace reads 1.0, so elapsed = 1.0 < 3.0 and it sleeps the 2.0
    # remainder; (3) second call then stamps _last_call again.
    ticks = iter([0.0, 1.0, 1.0])
    calls: list[float] = []
    opener = FakeOpener([{"posts": []}, {"posts": []}])
    c = PinboardClient(
        "user:TOK",
        opener=opener,
        sleep=calls.append,
        clock=lambda: next(ticks),
        min_interval=3.0,
    )
    c.get_recent()
    c.get_recent()
    assert calls == [2.0]  # 3.0 - 1.0 elapsed


def test_429_retries_then_raises():
    responses = [http_error(429)] * 5
    c, _, calls = make_client(responses, max_retries=3)
    with pytest.raises(RateLimitError):
        c.get_tags()
    assert len(calls) == 3


def test_401_maps_to_auth_error():
    c, _, _ = make_client([http_error(401, {"errorMessage": "bad token"})])
    with pytest.raises(AuthError):
        c.get_tags()


def test_dry_run_skips_writes_but_not_reads():
    c, opener, _ = make_client([{"posts": [{"description": "x"}]}], dry_run=True)
    c.delete_post("https://x")  # write: short-circuited
    assert opener.requests == []
    c.get_post("https://x")  # read: goes through
    assert len(opener.requests) == 1
