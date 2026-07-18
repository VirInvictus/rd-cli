"""Two-way additive sync between Raindrop and Pinboard.

Additive means the sync only ever *adds* and *merges*; it never deletes. Two
libraries converge to the union of their bookmarks, matched by a normalized URL
(which is also the dedup key). The model gap is bridged by encoding, reversibly,
in tags: a Raindrop collection becomes a slugged Pinboard tag, and Pinboard's
`toread`/Raindrop's `important` ride along as tags too. Highlights stay
Raindrop-only (Pinboard has no home for them).

The planning half (`plan_sync` and the mapping helpers) is pure and network-free
so it can be tested directly; `apply_plan` is the only part that writes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query keys that carry no identity; dropped before matching so tracking-tagged
# and clean copies of the same page dedup together. Real query params (e.g. an
# Anna's Archive search) are kept.
TRACKING = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_reader",
    "utm_name",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
    "ref_src",
    "ref_url",
    "spm",
    "yclid",
    "_hsenc",
    "_hsmi",
    "postshare",
    "share",
}


def normalize_url(url: str) -> str:
    """A comparison key: unify scheme to https, drop ``www.`` and the fragment,
    strip tracking params (but keep meaningful ones), and sort the rest."""
    p = urlsplit(url.strip())
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if p.port:
        host = f"{host}:{p.port}"
    path = p.path.rstrip("/") or "/"
    kept = sorted(
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in TRACKING
    )
    return urlunsplit(("https", host, path, urlencode(kept), ""))


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")


def raindrop_to_pinboard(rd: dict, coll_title_by_id: dict[int, str]) -> dict:
    """Fields for creating this raindrop on Pinboard."""
    tags = list(rd.get("tags") or [])
    cid = (rd.get("collection") or {}).get("$id")
    title = coll_title_by_id.get(cid) if cid is not None else None
    if title:
        slug = _slug(title)
        if slug and slug not in tags:
            tags.append(slug)
    if rd.get("important") and "important" not in tags:
        tags.append("important")
    note = (rd.get("note") or rd.get("excerpt") or "").strip()
    return {
        "url": rd["link"],
        "title": rd.get("title") or rd["link"],
        "extended": note,
        "tags": tags,
        "toread": False,
        "shared": True,
    }


def pinboard_to_raindrop(pb: dict, coll_id_by_slug: dict[str, int]) -> dict:
    """Fields for creating this Pinboard post as a raindrop. A tag that matches a
    Raindrop collection routes the item into it (and is dropped from the tag
    list); everything else lands in Unsorted."""
    collection_id = -1
    remaining: list[str] = []
    for t in (pb.get("tags") or "").split():
        cid = coll_id_by_slug.get(_slug(t))
        if cid is not None and collection_id == -1:
            collection_id = cid
        else:
            remaining.append(t)
    if pb.get("toread") == "yes" and "toread" not in remaining:
        remaining.append("toread")
    return {
        "link": pb["href"],
        "title": pb.get("description") or pb["href"],
        "note": (pb.get("extended") or "").strip(),
        "tags": remaining,
        "collection_id": collection_id,
    }


def merge_notes(a: str, b: str) -> str:
    """Keep both notes without duplicating on repeat syncs (idempotent)."""
    a, b = (a or "").strip(), (b or "").strip()
    if a == b or not b or b in a:
        return a
    if not a or a in b:
        return b
    return f"{a}\n\n{b}"


@dataclass
class SyncPlan:
    to_pinboard: list[dict] = field(default_factory=list)  # raindrop fields
    to_raindrop: list[dict] = field(default_factory=list)  # pinboard fields
    merges: list[dict] = field(
        default_factory=list
    )  # {"rd","pb","tags","rd_note","pb_note"}
    rd_dupes: int = 0
    pb_dupes: int = 0

    @property
    def total(self) -> int:
        return len(self.to_pinboard) + len(self.to_raindrop) + len(self.merges)


def plan_sync(
    raindrops: list[dict],
    pb_posts: list[dict],
    coll_title_by_id: dict[int, str],
    coll_id_by_slug: dict[str, int],
    rd_keep=None,
    pb_keep=None,
) -> SyncPlan:
    """Diff the two sides by normalized URL. Pure; no network.

    ``rd_keep``/``pb_keep`` are optional scope predicates: an item is only
    *pushed/merged* if its predicate passes, but matching always uses the full
    sets, so a scoped raindrop that also exists (unscoped) on the other side is
    still recognized and never re-imported as new.
    """
    rd_keep = rd_keep or (lambda rd: True)
    pb_keep = pb_keep or (lambda pb: True)
    rd_by_norm: dict[str, dict] = {}
    rd_dupes = 0
    for rd in raindrops:
        key = normalize_url(rd["link"])
        if key in rd_by_norm:
            rd_dupes += 1
        else:
            rd_by_norm[key] = rd
    pb_by_norm: dict[str, dict] = {}
    pb_dupes = 0
    for pb in pb_posts:
        key = normalize_url(pb["href"])
        if key in pb_by_norm:
            pb_dupes += 1
        else:
            pb_by_norm[key] = pb

    plan = SyncPlan(rd_dupes=rd_dupes, pb_dupes=pb_dupes)
    for key, rd in rd_by_norm.items():
        if key not in pb_by_norm and rd_keep(rd):
            plan.to_pinboard.append(raindrop_to_pinboard(rd, coll_title_by_id))
    for key, pb in pb_by_norm.items():
        rd = rd_by_norm.get(key)
        if rd is None:
            if pb_keep(pb):
                plan.to_raindrop.append(pinboard_to_raindrop(pb, coll_id_by_slug))
            continue
        # A merge touches both sides, so it must satisfy every active scope.
        if not (rd_keep(rd) and pb_keep(pb)):
            continue
        # On both: union tags (in each side's own vocabulary), merge notes.
        pb_as_rd = pinboard_to_raindrop(pb, coll_id_by_slug)
        rd_as_pb = raindrop_to_pinboard(rd, coll_title_by_id)
        rd_tags = sorted(set(rd.get("tags") or []) | set(pb_as_rd["tags"]))
        pb_tags = sorted(set((pb.get("tags") or "").split()) | set(rd_as_pb["tags"]))
        note = merge_notes(rd.get("note") or "", pb.get("extended") or "")
        rd_changed = set(rd_tags) != set(rd.get("tags") or []) or (
            note != (rd.get("note") or "").strip()
        )
        pb_changed = set(pb_tags) != set((pb.get("tags") or "").split()) or (
            note != (pb.get("extended") or "").strip()
        )
        if rd_changed or pb_changed:
            plan.merges.append(
                {
                    "rd": rd,
                    "pb": pb,
                    "rd_tags": rd_tags,
                    "pb_tags": pb_tags,
                    "note": note,
                    "rd_changed": rd_changed,
                    "pb_changed": pb_changed,
                }
            )
    return plan


def apply_plan(plan: SyncPlan, rd_client: Any, pb_client: Any) -> dict[str, int]:
    """Execute a plan. Honors each client's ``dry_run``. Returns a count summary."""
    counts = {"added_pinboard": 0, "added_raindrop": 0, "merged": 0}
    for fields in plan.to_pinboard:
        pb_client.add_post(
            fields["url"],
            fields["title"],
            extended=fields["extended"],
            tags=fields["tags"],
            shared=fields["shared"],
            toread=fields["toread"],
        )
        counts["added_pinboard"] += 1
    for fields in plan.to_raindrop:
        rd_client.create_raindrop(
            fields["link"],
            title=fields["title"],
            note=fields["note"],
            tags=fields["tags"],
            collection_id=fields["collection_id"],
        )
        counts["added_raindrop"] += 1
    for m in plan.merges:
        if m["rd_changed"]:
            rd_client.update_raindrop(m["rd"]["_id"], tags=m["rd_tags"], note=m["note"])
        if m["pb_changed"]:
            pb = m["pb"]
            pb_client.add_post(
                pb["href"],
                pb.get("description") or pb["href"],
                extended=m["note"],
                tags=m["pb_tags"],
                replace=True,
                shared=pb.get("shared") != "no",
                toread=pb.get("toread") == "yes",
            )
        counts["merged"] += 1
    return counts
