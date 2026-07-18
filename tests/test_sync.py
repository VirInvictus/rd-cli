from __future__ import annotations

from rd_cli import sync


def test_normalize_url_dedups_variants():
    a = sync.normalize_url("http://www.Example.com/path/?utm_source=x&b=2#frag")
    b = sync.normalize_url("https://example.com/path?b=2")
    assert a == b


def test_normalize_url_keeps_meaningful_query():
    # An Anna's Archive style search URL must NOT collapse to the bare host.
    u1 = sync.normalize_url("https://annas-archive.gl/search?q=dune")
    u2 = sync.normalize_url("https://annas-archive.gl/search?q=neuromancer")
    assert u1 != u2


def test_raindrop_to_pinboard_encodes_collection_and_important():
    rd = {
        "link": "https://x.com",
        "title": "X",
        "tags": ["ai"],
        "important": True,
        "collection": {"$id": 10},
    }
    out = sync.raindrop_to_pinboard(rd, {10: "Tabletop RPGs"})
    assert set(out["tags"]) == {"ai", "tabletop-rpgs", "important"}
    assert out["url"] == "https://x.com"


def test_pinboard_to_raindrop_routes_collection_tag():
    pb = {
        "href": "https://x.com",
        "description": "X",
        "tags": "tabletop-rpgs cooking",
        "toread": "yes",
    }
    out = sync.pinboard_to_raindrop(pb, {"tabletop-rpgs": 10})
    assert out["collection_id"] == 10
    assert "tabletop-rpgs" not in out["tags"]  # consumed by the collection route
    assert "cooking" in out["tags"]
    assert "toread" in out["tags"]  # toread flag becomes a tag


def test_pinboard_to_raindrop_unmatched_goes_unsorted():
    pb = {"href": "https://x.com", "description": "X", "tags": "cooking chef"}
    out = sync.pinboard_to_raindrop(pb, {"tabletop-rpgs": 10})
    assert out["collection_id"] == -1


def test_merge_notes_is_idempotent():
    merged = sync.merge_notes("alpha", "beta")
    assert "alpha" in merged and "beta" in merged
    # re-merging the combined note with a source must not duplicate it
    assert sync.merge_notes(merged, "beta") == merged
    assert sync.merge_notes("same", "same") == "same"


def test_plan_sync_splits_three_ways():
    raindrops = [
        {"_id": 1, "link": "https://only-rd.com", "tags": [], "collection": {"$id": 0}},
        {"_id": 2, "link": "https://both.com", "tags": ["a"], "collection": {"$id": 0}},
    ]
    pb_posts = [
        {"href": "https://only-pb.com", "description": "PB", "tags": "x"},
        {"href": "https://both.com", "description": "Both", "tags": "b"},
    ]
    plan = sync.plan_sync(raindrops, pb_posts, {}, {})
    assert [f["url"] for f in plan.to_pinboard] == ["https://only-rd.com"]
    assert [f["link"] for f in plan.to_raindrop] == ["https://only-pb.com"]
    assert len(plan.merges) == 1
    # the merge unions tags a + b on both sides
    m = plan.merges[0]
    assert set(m["rd_tags"]) == {"a", "b"}
    assert set(m["pb_tags"]) == {"a", "b"}


def test_plan_sync_counts_near_dupes():
    raindrops = [
        {"_id": 1, "link": "https://x.com/p", "tags": [], "collection": {"$id": 0}},
        {
            "_id": 2,
            "link": "https://x.com/p/?utm_source=t",
            "tags": [],
            "collection": {"$id": 0},
        },
    ]
    plan = sync.plan_sync(raindrops, [], {}, {})
    assert plan.rd_dupes == 1
    assert len(plan.to_pinboard) == 1  # the two collapse to one


def test_scope_narrows_push_but_not_matching():
    # A raindrop outside the scope still exists on Pinboard: it must NOT be
    # re-imported as new to Raindrop (matching uses the full set), it's just
    # not pushed the other way.
    raindrops = [
        {
            "_id": 1,
            "link": "https://in-scope.com",
            "tags": ["keep"],
            "collection": {"$id": 5},
        },
        {
            "_id": 2,
            "link": "https://out.com",
            "tags": ["skip"],
            "collection": {"$id": 9},
        },
    ]
    pb_posts = [{"href": "https://out.com", "description": "Out", "tags": ""}]
    plan = sync.plan_sync(
        raindrops,
        pb_posts,
        {},
        {},
        rd_keep=lambda r: (r.get("collection") or {}).get("$id") == 5,
    )
    # only the in-scope raindrop is pushed to pinboard
    assert [f["url"] for f in plan.to_pinboard] == ["https://in-scope.com"]
    # out.com is on both, so it is NOT re-added to raindrop despite being out of scope
    assert plan.to_raindrop == []


def test_plan_sync_no_op_when_identical():
    raindrops = [
        {
            "_id": 1,
            "link": "https://both.com",
            "tags": ["a"],
            "collection": {"$id": 0},
            "note": "",
        }
    ]
    pb_posts = [
        {"href": "https://both.com", "description": "B", "tags": "a", "extended": ""}
    ]
    plan = sync.plan_sync(raindrops, pb_posts, {}, {})
    assert plan.total == 0  # same tags, same (empty) note -> nothing to do
