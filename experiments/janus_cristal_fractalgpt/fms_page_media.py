#!/usr/bin/env python3
"""Resolve labeled FMDB specimen images without persisting their media bytes.

The resolver deliberately trusts only label metadata attached to the image tag
itself for primary selection. Broad neighboring page text is diagnostic only.
This avoids cross-associating adjacent Normal/LW/SW figures on specimen pages.
"""
from __future__ import annotations

import re
import urllib.request
from html import unescape

UA = "Janus-Cristal-FMS-resolver/0.2 (+https://github.com/Hawkar-usls/Janus_Genesis)"


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def _attr(tag: str, name: str) -> str | None:
    m = re.search(rf"\b{name}\s*=\s*([\"'])(.*?)\1", tag, flags=re.I | re.S)
    return unescape(m.group(2)) if m else None


def _largest_src_from_tag(tag: str) -> str | None:
    srcset = _attr(tag, "srcset") or _attr(tag, "data-srcset")
    if srcset:
        choices = []
        for item in srcset.split(","):
            item = item.strip()
            if not item:
                continue
            parts = item.split()
            url = parts[0]
            width = 0
            if len(parts) > 1 and parts[1].lower().endswith("w"):
                try:
                    width = int(parts[1][:-1])
                except ValueError:
                    pass
            choices.append((width, url))
        if choices:
            return max(choices)[1]
    return _attr(tag, "data-src") or _attr(tag, "src")


def _strip_html(s: str) -> str:
    s = re.sub(r"<script\b.*?</script>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<style\b.*?</style>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", unescape(s)).strip()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower().rstrip("."))


def media_candidates(page_url: str) -> list[dict]:
    html = _fetch_text(page_url)
    out = []
    for m in re.finditer(r"<img\b[^>]*>", html, flags=re.I | re.S):
        tag = m.group(0)
        src = _largest_src_from_tag(tag)
        if not src or src.startswith("data:"):
            continue
        start, end = m.span()
        pre = html[max(0, start - 500):start]
        post = html[end:min(len(html), end + 500)]
        out.append({
            "url": src,
            "alt": _attr(tag, "alt") or "",
            "title": _attr(tag, "title") or "",
            "context": _strip_html(pre + " " + post)[:700],
        })
    seen = set()
    unique = []
    for item in out:
        key = (item["url"], item["alt"], item["title"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def resolve_labeled_media(page_url: str, label: str) -> dict:
    label_norm = _norm(label)
    rows = media_candidates(page_url)

    exact = []
    for i, row in enumerate(rows):
        own_labels = [_norm(row["alt"]), _norm(row["title"])]
        if label_norm in own_labels:
            exact.append((i, row))
    if len(exact) == 1:
        i, best = exact[0]
        return {
            "label": label,
            "url": best["url"],
            "resolution_rule": "EXACT_IMAGE_OWN_ALT_OR_TITLE_MATCH",
            "candidate_count": len(rows),
            "exact_match_count": 1,
            "alt": best["alt"],
            "title": best["title"],
            "context_excerpt": best["context"][:500],
            "status": "RESOLVED_EXACT_IMAGE_OWN_LABEL",
        }
    if len(exact) > 1:
        raise RuntimeError(f"Ambiguous exact FMDB image-own label {label!r}: {len(exact)} matches")

    # Strict fallback: own alt/title must contain all meaningful label words.
    words = [w for w in re.findall(r"[a-z0-9]+", label_norm) if len(w) >= 3]
    fallback = []
    for i, row in enumerate(rows):
        own = _norm(" ".join([row["alt"], row["title"]]))
        if words and all(w in own for w in words):
            fallback.append((i, row))
    if len(fallback) != 1:
        raise RuntimeError(
            f"Could not uniquely resolve FMDB label from image-own metadata {label!r}; "
            f"exact={len(exact)} fallback={len(fallback)} candidates={len(rows)}"
        )
    _, best = fallback[0]
    return {
        "label": label,
        "url": best["url"],
        "resolution_rule": "ALL_LABEL_WORDS_IN_IMAGE_OWN_ALT_OR_TITLE",
        "candidate_count": len(rows),
        "exact_match_count": 0,
        "alt": best["alt"],
        "title": best["title"],
        "context_excerpt": best["context"][:500],
        "status": "RESOLVED_STRICT_IMAGE_OWN_LABEL_FALLBACK",
    }
