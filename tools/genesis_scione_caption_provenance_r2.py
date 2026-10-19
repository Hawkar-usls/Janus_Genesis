# -*- coding: utf-8 -*-
"""Inspect SciOne timestamped ASR captions without publishing their text.

The input is a *locally obtained* third-party subtitle HTML page. The normal
output is provenance, coverage, SHA-256 digests and chapter counts only. The
optional --inspect-window prints a short, temporary local research excerpt;
never commit that output or copy a complete third-party transcript to GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

VIDEO_ID = "aNrMBI0GYoU"
CHAPTER_BOUNDARIES = (
    ("INTRO_AND_POSITIONING", 0, 644),
    ("CAPABILITY_HORIZON", 644, 985),
    ("UNDESIRED_STRATEGY", 985, 1492),
    ("HIDDEN_BEHAVIOR", 1492, 1786),
    ("PHYSICAL_WORLD_ACCESS", 1786, 1993),
    ("STOPPABILITY", 1993, 2337),
    ("IRREVERSIBLE_HARM", 2337, 2640),
    ("OVERSIGHT_LIMITS", 2640, 2808),
    ("CREDITS_AND_CLOSE", 2808, 2900),
)


@dataclass(frozen=True)
class Segment:
    start_ms: int
    end_ms: int
    text: str


class _FilmotCaptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.segments: list[Segment] = []
        self._current: tuple[int, int] | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a" or self._current is not None:
            return
        fields = dict(attrs)
        if not re.fullmatch(r"a[0-9]+", fields.get("id") or ""):
            return
        if "d-s" not in fields or "d-e" not in fields:
            return
        try:
            start_ms = round(float(fields["d-s"] or "") * 1000)
            end_ms = round(float(fields["d-e"] or "") * 1000)
        except ValueError:
            return
        if start_ms < 0 or end_ms <= start_ms:
            return
        self._current = (start_ms, end_ms)
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current is not None:
            clean = " ".join("".join(self._parts).split())
            if clean:
                self.segments.append(Segment(*self._current, clean))
            self._current = None
            self._parts = []


def extract_segments(html: str) -> list[Segment]:
    parser = _FilmotCaptionParser()
    parser.feed(html)
    result = parser.segments
    if not result:
        raise ValueError("NO_TIMESTAMPED_CAPTION_SEGMENTS")
    if any(b.start_ms < a.start_ms for a, b in zip(result, result[1:])):
        raise ValueError("CAPTION_TIMELINE_NOT_MONOTONE")
    return result


def caption_provenance(source_bytes: bytes) -> dict:
    text = source_bytes.decode("utf-8")
    captions = extract_segments(text)
    canonical = "\n".join(
        f"{segment.start_ms}|{segment.end_ms}|{segment.text}" for segment in captions
    ).encode("utf-8")
    chapters = []
    for name, begin, end in CHAPTER_BOUNDARIES:
        matched = [seg for seg in captions if begin * 1000 <= seg.start_ms < end * 1000]
        chapter_bytes = "\n".join(
            f"{seg.start_ms}|{seg.end_ms}|{seg.text}" for seg in matched
        ).encode("utf-8")
        chapters.append({
            "chapter": name,
            "start_seconds": begin,
            "end_seconds": end,
            "subtitle_segments": len(matched),
            "text_sha256": hashlib.sha256(chapter_bytes).hexdigest(),
        })
    return {
        "schema": "janus.genesis.sci_one.asr_caption_provenance.v1",
        "source_video": f"https://www.youtube.com/watch?v={VIDEO_ID}",
        "extraction_source": f"https://filmot.com/video/{VIDEO_ID}",
        "caption_origin": "THIRD_PARTY_INDEX_OF_YOUTUBE_AUTOMATIC_SPEECH_RECOGNITION",
        "youtube_player_ru_caption_track_advertised": True,
        "subtitle_transcript_human_verified": False,
        "video_audio_independently_transcribed": False,
        "source_html_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "timestamped_text_sha256": hashlib.sha256(canonical).hexdigest(),
        "segments": len(captions),
        "first_start_ms": captions[0].start_ms,
        "last_end_ms": max(c.end_ms for c in captions),
        "chapters": chapters,
        "raw_subtitle_text_reproduced": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", required=True, type=Path)
    parser.add_argument("--inspect-window", nargs=2, type=float, metavar=("START_SEC", "END_SEC"))
    args = parser.parse_args()
    raw = args.html.read_bytes()
    if args.inspect_window:
        start, end = args.inspect_window
        if not 0 <= start < end <= 2900 or end - start > 540:
            raise ValueError("INSPECTION_WINDOW_INVALID_OR_TOO_LARGE")
        items = [seg for seg in extract_segments(raw.decode("utf-8"))
                 if start * 1000 <= seg.start_ms < end * 1000]
        for item in items:
            print(f"{item.start_ms / 1000:07.2f}s {item.text}")
    else:
        print(json.dumps(caption_provenance(raw), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
