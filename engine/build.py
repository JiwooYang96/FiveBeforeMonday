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
import collect
import research
import write

ROOT = Path(__file__).resolve().parent.parent
MAX_REWRITES = 2


def build(as_of=None, snapshot=None):
    log = []
    issue_id = (as_of or date.today()).isoformat()
    audit = {}
    status = {"issue": issue_id, "status": "held", "problems": [], "steps": log}
    try:
        snap = json.loads(Path(snapshot).read_text()) if snapshot else collect.collect(as_of)
        issue_id = status["issue"] = snap["week_end"]
        audit["snapshot"] = snap
        log.append(f"market data: {len(snap['stocks'])} stocks, {len(snap['indices'])} indices")
        evidence = research.research(snap)
        audit["evidence"] = evidence
        log.append(f"research: {len(evidence)} cited statements")

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
    a = ap.parse_args()
    s = build(date.fromisoformat(a.date) if a.date else None, a.snapshot)
    print(json.dumps(s, indent=2, ensure_ascii=False))
