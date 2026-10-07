"""Turn the saved output of a practice run into a per-task table and failure summary.

Usage (in ~/speedrun-kit):
    arena test --set practice --agent zeren-agent 2>&1 | tee runs/run2.txt
    python3 speedrun-agent/eval/parse_run.py runs/run2.txt            # prints the table
    python3 speedrun-agent/eval/parse_run.py runs/*.txt --summary     # failure categories across runs

Input is the text `arena test` prints: our [agent]/[debug] log lines plus the record at the end
(item number, outcome, seconds, points, task text, then `sent: ... expected: ...`).
Writes <file>.jsonl next to the input, one row per task.
"""
import collections
import json
import re
import sys

REC_ITEM = re.compile(r"^\s*(\d+)\s+(task|message)\s+(\w[\w ]*?)\s{2,}([\d.]+) s\s+(-?\d+)?\s*(.*)$")
REC_SENT = re.compile(r"^\s*sent:\s*(\{.*?\})\s+expected:\s*(.*)$")
AGENT = re.compile(r"^\[agent\] i0*(\d+) (ANSWER|SKIP) (.*?) in ([\d.]+)s \| (.*?) conf=(\S*) pages=(\d+)")
DEBUG = re.compile(r"^\[debug\] turn (\d+) ([\d.]+)s tokens=(\S+)/(\S+) (.*)$")
RUN_ID = re.compile(r"^Run (\S+)")
MODEL = re.compile(r"^\[llm\] model (\S+)")


def task_type(text):
    t = text.lower()
    if "new or established" in t or "new vs. established" in t or "established" in t:
        return "new_vs_established"
    if "referral" in t and "reason" in t:
        return "referral_reason"
    if "referral" in t and "practice" in t:
        return "referral_source"
    if "phone" in t:
        return "phone"
    return "other"


def category(row):
    """First-pass failure category. Wrong answers still need a human look at the [page] lines."""
    o = row["outcome"]
    why = (row.get("why") or "").lower()
    if o == "correct":
        return "ok"
    if o == "wrong":
        if row.get("conf") not in ("", None) and float(row["conf"]) >= 0.9:
            return "wrong:overconfident (calibration/retrieval: review pages)"
        return "wrong (review pages)"
    if o == "not reached":
        return "not reached (speed)"
    if "max turns" in why:
        return "skip:step budget exhausted (retrieval/tool selection)"
    if "time" == why.strip():
        return "skip:task time cap"
    if "low confidence" in why:
        return "skip:low confidence (calibration)"
    if "llm" in why or "error" in why:
        return "skip:error"
    if why:
        return "skip:model judged evidence missing (" + why[:60] + ")"
    return "skip:unknown"


def parse(path):
    rows, agent, debug_by_item, pending_debug = {}, {}, collections.defaultdict(list), []
    run_id, model = None, None
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if m := MODEL.match(ln):
            model = m.group(1)
        if m := DEBUG.match(ln):
            pending_debug.append({"turn": int(m.group(1)), "secs": float(m.group(2)),
                                  "in_tok": m.group(3), "out_tok": m.group(4), "calls": m.group(5)[:400]})
        if m := AGENT.match(ln):
            n = int(m.group(1))
            agent[n] = {"kind": m.group(2), "sent_value": m.group(3), "agent_secs": float(m.group(4)),
                        "why": m.group(5).strip(), "conf": m.group(6), "pages": int(m.group(7))}
            debug_by_item[n] = pending_debug
            pending_debug = []
        if m := RUN_ID.match(ln):
            run_id = m.group(1)
        if m := REC_ITEM.match(ln):
            n, kind, outcome, secs, pts, text = m.groups()
            if kind == "task":
                row = {"run": run_id, "model": model, "item": int(n), "outcome": outcome.strip(), "secs": float(secs),
                       "points": int(pts or 0), "task": text.strip(), "type": task_type(text)}
                if i + 1 < len(lines) and (s := REC_SENT.match(lines[i + 1])):
                    row["sent"] = s.group(1)
                    row["expected"] = s.group(2).strip()
                rows[int(n)] = row
        i += 1
    out = []
    for n, row in sorted(rows.items()):
        a = agent.get(n, {})
        row.update({k: a.get(k) for k in ("why", "conf", "pages")})
        dbg = debug_by_item.get(n, [])
        row["llm_turns"] = len(dbg) or None
        row["tool_calls"] = [d["calls"] for d in dbg]
        row["category"] = category(row)
        out.append(row)
    return out


def main(paths, summary):
    allrows = []
    for p in paths:
        rows = parse(p)
        allrows += rows
        with open(p + ".jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        if not summary:
            c = collections.Counter(r["outcome"] for r in rows)
            pts = sum(r["points"] for r in rows)
            print(f"\n{p}: run {rows[0]['run'] if rows else '?'}  points={pts}  " +
                  "  ".join(f"{k}={v}" for k, v in c.items()))
            for r in rows:
                print(f"  #{r['item']:<3} {r['outcome']:<11} {r['secs']:>5.1f}s {r['type']:<20} "
                      f"turns={r['llm_turns'] or '-':<3} sent={r.get('sent', '')[:40]:<42} "
                      f"expected={r.get('expected', '')[:40]}\n       -> {r['category']}")
    if summary or len(paths) > 1:
        print("\nFailure categories across", len(paths), "run(s):")
        for k, v in collections.Counter(r["category"] for r in allrows).most_common():
            print(f"  {v:>3}  {k}")
        print("\nBy task type (correct / wrong / skipped):")
        by = collections.defaultdict(collections.Counter)
        for r in allrows:
            by[r["type"]][r["outcome"]] += 1
        for t, c in sorted(by.items()):
            print(f"  {t:<20} {c['correct']} / {c['wrong']} / {c['skipped']}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args, "--summary" in sys.argv)
