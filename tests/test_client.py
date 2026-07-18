from __future__ import annotations

import json

import pytest

from conftest import FakeOpener, http_error
from rd_cli import client as client_mod
from rd_cli.client import RaindropClient
from rd_cli.errors import APIError, AuthError, NotFoundError, RateLimitError


def make_client(responses, **kwargs):
    calls = []
    opener = FakeOpener(responses)
    c = RaindropClient("tok", opener=opener, sleep=lambda s: calls.append(s), **kwargs)
    return c, opener, calls


def body_of(req) -> dict:
    return json.loads(req.data.decode())


# -- request construction -----------------------------------------------------


def test_auth_header_and_user_agent_present():
    c, opener, _ = make_client([{"item": {}}])
    c.get_raindrop(5)
    req = opener.last
    assert req.get_header("Authorization") == "Bearer tok"
    assert "rd-cli/" in req.get_header("User-agent")
    assert req.get_method() == "GET"
    assert req.full_url.endswith("/raindrop/5")


def test_boolean_query_params_are_lowercased():
    c, opener, _ = make_client([{"items": []}])
    c.get_raindrops(0, nested=True)
    assert "nested=true" in opener.last.full_url
    assert "True" not in opener.last.full_url


def test_perpage_clamped_to_max():
    c, opener, _ = make_client([{"items": []}])
    c.get_raindrops(0, perpage=500)
    assert "perpage=50" in opener.last.full_url


def test_create_raindrop_builds_collection_shape():
    c, opener, _ = make_client([{"item": {"_id": 1}}])
    c.create_raindrop("https://x.com", collection_id=42, tags=["a"], please_parse=True)
    payload = body_of(opener.last)
    assert payload["link"] == "https://x.com"
    assert payload["collection"] == {"$id": 42}
    assert payload["tags"] == ["a"]
    assert payload["pleaseParse"] == {}
    assert opener.last.get_method() == "POST"


def test_delete_raindrops_sends_ids_body_on_delete():
    c, opener, _ = make_client([{"modified": 3}])
    n = c.delete_raindrops(10, ids=[1, 2, 3])
    assert n == 3
    assert opener.last.get_method() == "DELETE"
    assert body_of(opener.last) == {"ids": [1, 2, 3]}


def test_update_raindrop_drops_none_fields():
    c, opener, _ = make_client([{"item": {}}])
    c.update_raindrop(1, title="New", tags=None, note=None)
    assert body_of(opener.last) == {"title": "New"}


def test_update_raindrops_move_to_builds_collection_and_path_scope():
    c, opener, _ = make_client([{"modified": 2}])
    n = c.update_raindrops(-1, ids=[1, 2], move_to=42)
    assert n == 2
    # Path scope is the SOURCE (-1), destination goes in the body.
    assert opener.last.full_url.endswith("/raindrops/-1")
    body = body_of(opener.last)
    assert body["collection"] == {"$id": 42}
    assert body["ids"] == [1, 2]


def test_delete_raindrop_permanent_deletes_twice():
    # First delete -> trash; second delete -> permanent.
    c, opener, _ = make_client([{"result": True}, {"result": True}])
    assert c.delete_raindrop(5, permanent=True) is True
    assert len(opener.requests) == 2
    assert all(r.get_method() == "DELETE" for r in opener.requests)


def test_delete_raindrop_permanent_tolerates_second_404():
    # Item already in trash: first delete removes it, second 404s (swallowed).
    c, _, _ = make_client([{"result": True}, http_error(404)])
    assert c.delete_raindrop(5, permanent=True) is True


def test_dry_run_short_circuits_writes_but_not_reads():
    # No responses queued for the write; a read still hits the (fake) transport.
    c, opener, _ = make_client([{"item": {"_id": 1}}], dry_run=True)
    # write: returns synthetic dict without touching the opener
    assert c.delete_raindrop(9) is True
    assert opener.requests == []
    # read: still goes through
    assert c.get_raindrop(1)["_id"] == 1
    assert len(opener.requests) == 1


def test_dry_run_preview_distinguishes_body_kinds():
    # JSON body -> the JSON; multipart -> a <multipart ...> tag; neither -> <no body>.
    assert client_mod._dry_run_preview({"a": 1}, None, None) == '{"a": 1}'
    assert client_mod._dry_run_preview(None, None, None) == "<no body>"
    multipart = client_mod._dry_run_preview(
        None, {"file": ("a.txt", b"x", "text/plain")}, {"collectionId": "5"}
    )
    assert multipart.startswith("<multipart ")
    assert "files=[file]" in multipart


def test_dry_run_bodyless_delete_not_labeled_multipart(capsys):
    # Regression: a plain DELETE has no body and must not read as <multipart>.
    c, _, _ = make_client([], dry_run=True)
    c.delete_raindrop(9)
    err = capsys.readouterr().err
    assert "DRY RUN DELETE /raindrop/9 <no body>" in err
    assert "multipart" not in err


def test_retry_after_http_date_parsed():
    from email.utils import formatdate

    future = formatdate(9_999_999_999)  # far-future HTTP-date
    c, _, calls = make_client(
        [http_error(429, headers={"Retry-After": future}), {"user": {}}]
    )
    c.get_user()
    assert len(calls) == 1
    assert 0 <= calls[0] <= 60  # capped


# -- error mapping ------------------------------------------------------------


def test_401_maps_to_auth_error():
    c, _, _ = make_client([http_error(401, {"errorMessage": "Unauthorized"})])
    with pytest.raises(AuthError) as ei:
        c.get_user()
    assert ei.value.status == 401
    assert "Unauthorized" in str(ei.value)


def test_404_maps_to_not_found():
    c, _, _ = make_client([http_error(404, {"errorMessage": "not found"})])
    with pytest.raises(NotFoundError):
        c.get_raindrop(999)


def test_error_message_parsed_from_body():
    c, _, _ = make_client([http_error(400, {"errorMessage": "bad view"})])
    with pytest.raises(APIError) as ei:
        c.create_collection("x", view="bogus")
    assert "bad view" in str(ei.value)


# -- retry / backoff ----------------------------------------------------------


def test_retries_on_500_then_succeeds():
    c, opener, calls = make_client([http_error(500), {"item": {"_id": 7}}])
    item = c.get_raindrop(7)
    assert item["_id"] == 7
    assert len(calls) == 1  # slept once between attempts


def test_429_retries_then_raises_ratelimit():
    responses = [http_error(429, headers={"Retry-After": "0"})] * 5
    c, _, calls = make_client(responses, max_retries=3)
    with pytest.raises(RateLimitError):
        c.get_user()
    assert len(calls) == 3  # max_retries sleeps, then give up


def test_retry_after_header_respected():
    c, _, calls = make_client(
        [http_error(429, headers={"Retry-After": "2"}), {"user": {}}]
    )
    c.get_user()
    assert calls == [2.0]


# -- pagination ---------------------------------------------------------------


def test_iter_raindrops_stops_on_short_page():
    full = {"items": [{"_id": i} for i in range(50)]}
    short = {"items": [{"_id": 50}]}
    c, _, _ = make_client([full, short])
    out = list(c.iter_raindrops(0))
    assert len(out) == 51


def test_iter_raindrops_single_short_page():
    c, opener, _ = make_client([{"items": [{"_id": 1}, {"_id": 2}]}])
    out = list(c.iter_raindrops(0))
    assert len(out) == 2
    assert len(opener.requests) == 1


# -- helpers ------------------------------------------------------------------


def test_encode_params_lowercases_bool_and_drops_none():
    assert client_mod._encode_params({"a": True, "b": None, "c": 3}) == "a=true&c=3"


def test_multipart_contains_boundary_and_parts():
    body, ctype = client_mod._multipart(
        {"file": ("a.txt", b"hello", "text/plain")}, {"collectionId": "5"}
    )
    assert ctype.startswith("multipart/form-data; boundary=")
    assert b'name="collectionId"' in body
    assert b'filename="a.txt"' in body
    assert b"hello" in body


def test_collection_payload_parent_shape():
    payload = client_mod._collection_payload(title="X", parent_id=9)
    assert payload == {"title": "X", "parent": {"$id": 9}}
