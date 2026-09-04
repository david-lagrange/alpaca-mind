#!/usr/bin/env python3
"""render_transcript — turn a session's stream-json .jsonl into readable markdown.

The JSONL transcripts are MORE complete than the interactive CLI view
(tool results are untruncated). This renders them for human audit and
for the Coach's session-transcript reviews.

Usage:
  render_transcript.py logs/sessions/20260708T140000Z-routine.jsonl [-o out.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonlog import get_logger

log = get_logger("render_transcript")


def clip(text: str, n: int = 3000) -> str:
    text = str(text)
    return text if len(text) <= n else text[:n] + f"\n… [{len(text) - n} chars clipped]"


def render(path: Path) -> str:
    out = [f"# Session transcript — `{path.name}`\n"]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.error("transcript_read_failed", exc=e, path=str(path))
        raise
    for line_no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError as e:
            log.error("transcript_line_parse_failed", exc=e,
                      path=str(path), line_no=line_no)
            continue
        t = evt.get("type")

        if t == "system" and evt.get("subtype") == "init":
            out.append(f"**Init** — model `{evt.get('model')}`, "
                       f"session `{evt.get('session_id')}`\n")

        elif t == "system":
            # Every other system line renders too — task_notification
            # carries an async subagent's ENTIRE result, and dropping it
            # makes real delegated work invisible to transcript-based
            # review (a reader would wrongly conclude the consult never
            # returned). Unknown shapes fall back to clipped JSON rather
            # than silence.
            sub = evt.get("subtype") or "system"
            payload = None
            for k in ("result", "summary", "message", "content", "text"):
                v = evt.get(k)
                if isinstance(v, str) and v.strip():
                    payload = v
                    break
            if payload is None:
                small = {k: v for k, v in evt.items()
                         if k not in ("type", "session_id", "uuid")}
                payload = json.dumps(small, indent=2, default=str)
            out.append(f"<details><summary>📨 system: {sub}</summary>\n\n"
                       f"{clip(payload, 4000)}\n\n</details>\n")

        elif t == "assistant":
            for block in (evt.get("message") or {}).get("content", []):
                bt = block.get("type")
                if bt == "text" and block.get("text", "").strip():
                    out.append(f"### 🤖 Assistant\n\n{block['text']}\n")
                elif bt == "thinking" and block.get("thinking", "").strip():
                    out.append("<details><summary>💭 thinking</summary>\n\n"
                               f"{clip(block['thinking'], 2000)}\n\n</details>\n")
                elif bt == "tool_use":
                    args = json.dumps(block.get("input", {}), indent=2,
                                      default=str)
                    out.append(f"**🔧 {block.get('name')}**\n\n"
                               f"```json\n{clip(args, 1500)}\n```\n")

        elif t == "user":
            for block in (evt.get("message") or {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content")
                    if isinstance(content, list):
                        content = "\n".join(
                            c.get("text", "") for c in content
                            if isinstance(c, dict))
                    out.append("<details><summary>↩︎ tool result</summary>\n\n"
                               f"```\n{clip(content)}\n```\n\n</details>\n")

        elif t == "result":
            out.append(
                "---\n\n## Result\n\n"
                f"- subtype: `{evt.get('subtype')}`\n"
                f"- turns: {evt.get('num_turns')}\n"
                f"- duration: {(evt.get('duration_ms') or 0) / 1000:.0f}s\n\n"
                f"{evt.get('result') or ''}\n")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()
    md = render(Path(args.transcript))
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
