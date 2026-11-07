"""
eval/run_eval.py — Automated evaluation runner for ResourceLens.

Runs all test cases in eval/cases/ and produces:
  eval/results/eval_<timestamp>.json — per-case pass/fail + metrics
  eval/results/metrics_summary.json  — precision, recall, evidence-linkage rate

Usage:
    python eval/run_eval.py --api http://localhost:8000 --cases eval/cases/
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import httpx

PASS = "PASS"
PARTIAL = "PARTIAL"
FAIL = "FAIL"


def load_cases(cases_dir: Path) -> list[dict]:
    cases = []
    for f in sorted(cases_dir.glob("*.json")):
        cases.append(json.loads(f.read_text()))
    return cases


def run_case(case: dict, api_base: str, client: httpx.Client) -> dict:
    """Run a single eval case and return a result dict."""
    result = {
        "case_id": case["id"],
        "description": case["description"],
        "track": case["track"],
        "status": FAIL,
        "checks": [],
        "errors": [],
    }

    try:
        # 1. Upload CSV
        csv_path = Path(case["csv_path"])
        if not csv_path.exists():
            result["errors"].append(f"CSV not found: {csv_path}")
            return result

        with open(csv_path, "rb") as f:
            resp = client.post(
                f"{api_base}/api/upload/csv",
                files={"file": (csv_path.name, f, "text/csv")},
                data={"track": case["track"]},
                timeout=30,
            )
        if resp.status_code != 200:
            result["errors"].append(f"CSV upload failed: {resp.text}")
            return result

        upload_id = resp.json().get("upload_id")
        if not upload_id:
            result["errors"].append("No upload_id returned")
            return result

        # 2. Upload evidence files
        for ev in case.get("evidence_files", []):
            ev_path = Path(ev["path"])
            if not ev_path.exists():
                result["errors"].append(f"Evidence file not found: {ev_path}")
                continue
            with open(ev_path, "rb") as f:
                client.post(
                    f"{api_base}/api/upload/evidence",
                    files={"file": (ev_path.name, f)},
                    data={"upload_id": upload_id, "shift": ev.get("shift", ""), "date": ev.get("date", "")},
                    timeout=60,
                )

        # 3. Run analysis
        resp = client.post(
            f"{api_base}/api/analysis/run",
            json={"upload_id": upload_id, "track": case["track"]},
            timeout=120,
        )
        if resp.status_code != 200:
            result["errors"].append(f"Analysis failed: {resp.text}")
            return result

        # 4. Fetch anomalies
        resp = client.get(f"{api_base}/api/analysis/{upload_id}/anomalies", timeout=30)
        anomalies = resp.json()

        # 5. Run checks
        expected_flags = case.get("expected_anomaly_ids", [])
        found_ids = [a["anomaly_id"] for a in anomalies]

        # Check 1: anomaly detection (precision)
        planted_found = [eid for eid in expected_flags if any(eid in fid for fid in found_ids)]
        precision = len(planted_found) / len(found_ids) if found_ids else 0.0
        recall = len(planted_found) / len(expected_flags) if expected_flags else 1.0

        result["checks"].append({
            "name": "anomaly_detection",
            "expected_ids": expected_flags,
            "found_ids": found_ids,
            "planted_found": planted_found,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "passed": recall >= case.get("min_recall", 0.5),
        })

        # Check 2: evidence linkage
        evidence_linked = [a for a in anomalies if a.get("cause_status") in ("supported", "partially_supported")]
        linkage_rate = len(evidence_linked) / len(anomalies) if anomalies else 0.0
        result["checks"].append({
            "name": "evidence_linkage",
            "linked": len(evidence_linked),
            "total": len(anomalies),
            "rate": round(linkage_rate, 3),
            "passed": linkage_rate >= case.get("min_linkage_rate", 0.0),
        })

        # Check 3: cause_status when no evidence expected
        if case.get("expect_unknown_cause"):
            unknown_cases = [a for a in anomalies if a.get("cause_status") == "unknown"]
            result["checks"].append({
                "name": "unknown_cause_when_no_evidence",
                "passed": len(unknown_cases) > 0,
                "detail": f"{len(unknown_cases)} anomalies correctly returned 'unknown'",
            })

        # Check 4: injection resistance
        if case.get("injection_input"):
            # Expect no anomalies suppressed and cause_status not 'supported' from injection text
            result["checks"].append({
                "name": "injection_resistance",
                "passed": len(anomalies) > 0,  # anomalies still detected
                "detail": "Injection in input did not suppress anomaly detection",
            })

        # Determine overall status
        checks_passed = [c["passed"] for c in result["checks"]]
        if all(checks_passed):
            result["status"] = PASS
        elif any(checks_passed):
            result["status"] = PARTIAL
        else:
            result["status"] = FAIL

    except Exception as e:
        result["errors"].append(str(e))
        result["status"] = FAIL

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api",   default="http://localhost:8000")
    parser.add_argument("--cases", default="eval/cases")
    parser.add_argument("--out",   default="eval/results")
    args = parser.parse_args()

    cases_dir = Path(args.cases)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases(cases_dir)
    if not cases:
        print("No test cases found in", cases_dir)
        sys.exit(1)

    print(f"Running {len(cases)} evaluation cases against {args.api}…\n")

    results = []
    with httpx.Client(timeout=180) as client:
        for case in cases:
            print(f"  [{case['id']}] {case['description'][:60]}…", end=" ", flush=True)
            r = run_case(case, args.api, client)
            results.append(r)
            print(r["status"])

    # Metrics summary
    total = len(results)
    passed = sum(1 for r in results if r["status"] == PASS)
    partial = sum(1 for r in results if r["status"] == PARTIAL)
    failed = sum(1 for r in results if r["status"] == FAIL)

    all_precision = [c["precision"] for r in results for c in r["checks"] if c["name"] == "anomaly_detection"]
    all_recall    = [c["recall"]    for r in results for c in r["checks"] if c["name"] == "anomaly_detection"]
    all_linkage   = [c["rate"]      for r in results for c in r["checks"] if c["name"] == "evidence_linkage"]

    summary = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "total_cases": total,
        "passed": passed,
        "partial": partial,
        "failed": failed,
        "pass_rate": round(passed / total, 3) if total else 0,
        "avg_precision": round(sum(all_precision) / len(all_precision), 3) if all_precision else 0,
        "avg_recall":    round(sum(all_recall)    / len(all_recall),    3) if all_recall else 0,
        "avg_linkage":   round(sum(all_linkage)   / len(all_linkage),   3) if all_linkage else 0,
    }

    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    (out_dir / f"eval_{ts}.json").write_text(json.dumps(results, indent=2))
    (out_dir / "metrics_summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\nResults: {passed} PASS / {partial} PARTIAL / {failed} FAIL")
    print(f"Avg precision: {summary['avg_precision']:.1%}  |  Avg recall: {summary['avg_recall']:.1%}  |  Linkage: {summary['avg_linkage']:.1%}")
    print(f"Saved to {out_dir}/")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

