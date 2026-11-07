"""T2: one direct model call, no agent, no tools. Notes picked by plain local search.

Also counts tokens for each T1 component with the count_tokens endpoint, so both
runs are broken down the same way. Writes t2-result.json and components.json here.
"""

import json
import re
import time
from pathlib import Path

import anthropic

MODEL = "claude-opus-5-5"
HERE = Path(__file__).parent
BRAIN = Path(r"C:\Users\shman\yggdras-brain\demo-brain")
SKILL = Path(r"C:\Users\shman\OneDrive\Desktop\Yggdrass OS\Yggdrass-OS\skills\gateway\SKILL.md")
QUESTION = "Who replaced Ken Mattingly on Apollo 13, and why?"
INSTRUCTION = (
    "Answer the question using only the notes below; add nothing of your own.\n"
    "Cite the note path after each fact. If the notes do not contain the answer, say \"I don't have that\"."
)
KEYWORDS = [r"mattingly", r"apollo[ -]13", r"replac"]
TOP_N = 3


def pick_notes() -> list[tuple[int, Path]]:
    """Rank notes (index.md excluded) by total keyword hits; ties keep path order."""
    scored = []
    for f in sorted(BRAIN.rglob("*.md")):
        if f.name == "index.md":
            continue
        text = f.read_text(encoding="utf-8").lower()
        hits = sum(len(re.findall(k, text)) for k in KEYWORDS)
        if hits:
            scored.append((hits, f))
    scored.sort(key=lambda x: -x[0])
    return scored[:TOP_N]


def count(client: anthropic.Anthropic, text: str) -> int:
    """Tokens for `text` alone, minus the fixed cost of a one-character message."""
    n = client.messages.count_tokens(model=MODEL, messages=[{"role": "user", "content": text}])
    base = client.messages.count_tokens(model=MODEL, messages=[{"role": "user", "content": "x"}])
    return n.input_tokens - base.input_tokens


def main() -> None:
    client = anthropic.Anthropic()
    ranked = pick_notes()
    notes = [(f.relative_to(BRAIN).as_posix(), f.read_text(encoding="utf-8")) for _, f in ranked]
    note_block = "\n\n".join(f"=== {p} ===\n{t}" for p, t in notes)
    prompt = f"{INSTRUCTION}\n\nQuestion: {QUESTION}\n\nNotes:\n\n{note_block}"

    start = time.perf_counter()
    resp = client.messages.create(
        model=MODEL, max_tokens=1024, messages=[{"role": "user", "content": prompt}]
    )
    seconds = time.perf_counter() - start
    answer = "".join(b.text for b in resp.content if b.type == "text")

    t2 = {
        "model": resp.model,
        "ranking": [(h, f.relative_to(BRAIN).as_posix()) for h, f in ranked],
        "usage": resp.usage.model_dump(),
        "seconds": round(seconds, 2),
        "parts": {
            "instruction": count(client, INSTRUCTION),
            "question": count(client, f"Question: {QUESTION}"),
            "notes": {p: count(client, f"=== {p} ===\n{t}") for p, t in notes},
        },
        "answer": answer,
        "answer_tokens": resp.usage.output_tokens,
    }
    (HERE / "t2-result.json").write_text(json.dumps(t2, indent=2), encoding="utf-8")

    # T1 components, counted as raw text (tool-result wrapping adds a few tokens each).
    t1_files = ["index.md", "topics/rubella-crew-swap.md", "people/jack-swigert.md"]
    comp = {
        "skill": count(client, SKILL.read_text(encoding="utf-8")),
        "index": count(client, (BRAIN / "index.md").read_text(encoding="utf-8")),
        "notes": {p: count(client, (BRAIN / p).read_text(encoding="utf-8")) for p in t1_files[1:]},
        "question": count(client, f"Question: {QUESTION}"),
    }
    (HERE / "components.json").write_text(json.dumps(comp, indent=2), encoding="utf-8")
    print(json.dumps({"t2": t2, "t1_components": comp}, indent=2))


if __name__ == "__main__":
    main()
