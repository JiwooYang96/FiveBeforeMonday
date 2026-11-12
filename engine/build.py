"""Build this week's issue end to end.

collect market data -> research (cited) -> write -> gates (rewrite up to twice) ->
fact-check review -> render charts and emails.

Writes engine/data/<issue>.json, engine/data/audit/<issue>.json (data, evidence, every
check result) and build-status.json, which the workflow reads to decide whether to
schedule the send or hold the issue as a draft.

Usage: python3 engine/build.py [--date YYYY-MM-DD] [--snapshot path.json]
"""
import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import check
import llm
import collect
import research
import verify_research
import write

ROOT = Path(__file__).resolve().parent.parent
MAX_REWRITES = 2


def get_evidence(snap, log, audit):
    """Claude Code's research file if it exists and holds up; otherwise research through the API."""
    path = ROOT / "engine/data/research" / f"{snap['week_end']}.json"
    if path.exists():
        try:
            evidence, dropped = verify_research.load(path)
            confirmed = sum(1 for e in evidence for s in e["sources"] if s.get("verified"))
            log.append(f"research (Claude Code): {len(evidence)} statements kept, {confirmed} quotes confirmed "
                       f"on the page, {len(dropped)} dropped")
            audit["research_dropped"] = dropped
            if len(evidence) >= 8:
                return evidence
            log.append("too few statements survived; falling back to API research")
        except Exception as err:
            log.append(f"research file unusable ({err}); falling back to API research")
    else:
        log.append("no Claude Code research for this week; using API research")
    evidence = research.research(snap)
    log.append(f"research (API): {len(evidence)} cited statements")
    return evidence


def build(as_of=None, snapshot=None, skip_if_built=False):
    log = []
    monday, friday = collect.trading_week(as_of)
    issue_id = friday.isoformat()
    audit = {}
    status = {"issue": issue_id, "status": "held", "problems": [], "steps": log}
    if skip_if_built and (ROOT / "engine/data" / f"{issue_id}.json").exists():
        status["status"] = "skipped"
        (ROOT / "build-status.json").write_text(json.dumps(status, indent=2))
        return status
    try:
        raw = ROOT / "engine/data/raw" / f"{issue_id}.json"
        if snapshot:
            snap = json.loads(Path(snapshot).read_text())
        elif raw.exists():
            snap = json.loads(raw.read_text())
        else:
            snap = collect.collect(as_of)
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(json.dumps(snap, indent=2))
        issue_id = status["issue"] = snap["week_end"]
        audit["snapshot"] = snap
        log.append(f"market data: {len(snap['stocks'])} stocks, {len(snap['indices'])} indices")
        evidence = get_evidence(snap, log, audit)
        audit["evidence"] = evidence

        d = write.draft(snap, evidence)
        problems = check.run(d, snap, evidence)
        for attempt in range(MAX_REWRITES):
            if not problems:
                break
            log.append(f"draft {attempt + 1}: {len(problems)} problems, rewriting")
            audit.setdefault("rejected", []).append({"draft": d, "problems": problems})
            d = write.draft(snap, evidence, feedback=problems, previous=d)
            problems = check.run(d, snap, evidence)

        if not problems:
            notes, blocking = check.review(d, snap, evidence)
            log.append(f"review: {len(notes)} notes")
            if blocking:
                audit.setdefault("rejected", []).append({"draft": d, "problems": notes})
                d = write.draft(snap, evidence, feedback=notes, previous=d)
                problems = check.run(d, snap, evidence)
                if not problems:
                    notes, blocking = check.review(d, snap, evidence)
                    problems = notes if blocking else []
        audit["final_draft"] = d
        status["problems"] = problems
        status["status"] = "ready" if not problems else "held"
        status["saturday_subject"] = d.get("saturday", {}).get("subject")
        status["sunday_subject"] = d.get("sunday", {}).get("subject")

        issue = write.assemble(snap, d)
        issue_path = ROOT / "engine/data" / f"{issue_id}.json"
        issue_path.write_text(json.dumps(issue, indent=2, ensure_ascii=False))
        subprocess.run([sys.executable, str(ROOT / "engine/charts.py"), str(issue_path), str(ROOT / "img")], check=True)
        subprocess.run([sys.executable, str(ROOT / "engine/emails.py"), str(issue_path), str(ROOT / "emails/out")],
                       check=True)
        log.append("rendered charts and emails")
    except Exception as err:  # any failure holds the issue; nothing is sent
        status["status"] = "failed"
        status["problems"].append(f"{type(err).__name__}: {err}")
    finally:
        status["usage"] = {**llm.USAGE, "est_cost_usd": llm.cost()}
        log.append(f"API use: {llm.USAGE['input']:,} in / {llm.USAGE['output']:,} out tokens, "
                   f"{llm.USAGE['cache_read']:,} cached, {llm.USAGE['searches']} searches, about ${llm.cost():.2f}")
        if write.RAW:
            audit["writer_raw"] = write.RAW
        if research.LAST_BLOCKS:
            audit["research_raw"] = research.LAST_BLOCKS
        audit_dir = ROOT / "engine/data/audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / f"{issue_id}.json").write_text(json.dumps({**audit, "status": status}, indent=2,
                                                               ensure_ascii=False))
        (ROOT / "build-status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))
    return status


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--snapshot")
    ap.add_argument("--skip-if-built", action="store_true")
    a = ap.parse_args()
    s = build(date.fromisoformat(a.date) if a.date else None, a.snapshot, a.skip_if_built)
    print(json.dumps(s, indent=2, ensure_ascii=False))
