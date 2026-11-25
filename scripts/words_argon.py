"""Writes the texts the web page has no need of, one file an area: `src/hmz/words/argon/*.json`.

The command line and the terminal interface say what the page says, in the page's words
(`src/hmz/words/gui`). What only they say -- a line of `--help`, a key hint -- is written by one
model in the page's voice rather than by whoever wrote the code around it, so that the three
interfaces read as one. An area keeps its texts in a file of its own:

    {"entries": [{"wants": "what the text has to say", "where": "where it is read", "text": ""}]}

This fills each `text` left empty (every one with `--redo`) and keeps the model beside them. An
entry counting something with `{n}` has a `"one": ""` beside its `text`, which is filled with
what it is for exactly one.

    ARGON_API_KEY=… uv run python scripts/words_argon.py src/hmz/words/argon/devices.json

The key is read from the environment and written nowhere.
"""

from __future__ import annotations

import json
import os
import random
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUI = ROOT / "src/hmz/words/gui/en.json"
URL = os.environ.get("ARGON_API_URL", "https://inference-api.nvidia.com/v1")
MODEL = os.environ.get("ARGON_MODEL", "gcp/google/gemini-4-argon")

#: How many of the page's own texts the model is shown, the same ones every time.
_SHOWN = 160

_VOICE = """\
You write the interface text of Humanize (`hmz`), a tool that runs AI agents on a person's own \
machines. Its web page already has a voice, shown below in its own texts. You are writing texts \
for its command line (`--help` lines, messages) and its terminal interface (labels, key hints), \
which must read as the same product.

Rules:
- Use the page's nouns exactly: chat, epic, flow, flowverse, workspace, folder, environment, \
runtime, account, nous, daemon, device, side question, Ai-chan, harness session, backup, board.
- Plain present-tense English, British spelling, no marketing, no exclamation marks, no emoji.
- Say what a thing does, not that it "allows you to" do it. No "please", no "simply".
- Sentence case. A label or a summary has no full stop; a sentence has one.
- A `--help` summary starts with a lower-case verb and stays under 12 words. Any single text \
stays under 30 words unless its entry says otherwise.
- Keep `{names}` in braces and anything in backticks exactly as the entry gives them.
- Where one of the page's own texts already says it, answer with that text unchanged.

Answer with a JSON array of strings only, one text per entry, in the entries' order.
"""


def asked(entries: list[dict[str, str]]) -> list[str]:
    """What the model writes for each entry, in their order."""
    page = sorted(json.loads(GUI.read_text(encoding="utf-8")))
    shown = random.Random(0).sample(page, _SHOWN)  # noqa: S311 -- a sample, not a secret
    wanted = [
        {"wants": entry["wants"], "where": entry.get("where", "")} for entry in entries
    ]
    body = {
        "model": MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _VOICE},
            {
                "role": "user",
                "content": "The page's own texts:\n"
                + json.dumps(shown, ensure_ascii=False)
                + "\n\nWrite these:\n"
                + json.dumps(wanted, ensure_ascii=False, indent=1),
            },
        ],
    }
    request = urllib.request.Request(  # noqa: S310 -- the address is https, or what was asked for
        URL.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['ARGON_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as answer:  # noqa: S310
        said = json.load(answer)["choices"][0]["message"]["content"]
    said = said.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    texts = json.loads(said)
    if not isinstance(texts, list) or len(texts) != len(entries):
        raise SystemExit(f"asked for {len(entries)} texts and was answered {said!r}")
    return [str(text) for text in texts]


def main(argv: list[str]) -> int:
    """Fills the files named on the line, and says how many texts each was written."""
    redo = "--redo" in argv
    paths = [Path(arg) for arg in argv if not arg.startswith("--")]
    if not paths or "ARGON_API_KEY" not in os.environ:
        print(__doc__, file=sys.stderr)
        return 2
    for path in paths:
        kept = json.loads(path.read_text(encoding="utf-8"))
        wanting = [entry for entry in kept["entries"] if redo or not entry.get("text")]
        # Each entry that counts is asked for twice: for many, and for exactly one.
        asks = [(entry, "text", entry["wants"]) for entry in wanting]
        asks += [
            (entry, "one", entry["wants"] + " -- written for exactly one (n is 1)")
            for entry in wanting
            if "one" in entry
        ]
        # A few dozen at a time: one answer short of an entry is the whole call again.
        for at in range(0, len(asks), 40):
            batch = asks[at : at + 40]
            wanted = [
                {"wants": wants, "where": entry.get("where", "")}
                for entry, _, wants in batch
            ]
            for (entry, form, _), text in zip(batch, asked(wanted), strict=True):
                entry[form] = text
        kept["model"] = MODEL
        path.write_text(
            json.dumps(kept, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"{path}: {len(wanting)} written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
