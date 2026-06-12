#!/usr/bin/env python3
"""Audit Merak Plan Mode evidence against the planning UX goal."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "merak-plan-audit"


@dataclass(frozen=True)
class AuditItem:
    id: str
    requirement: str
    passed: bool
    evidence: tuple[str, ...]
    notes: tuple[str, ...] = ()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modal-spend-file",
        type=Path,
        help="Optional Modal post-run spend/container snapshot JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for audit JSON and Markdown reports.",
    )
    args = parser.parse_args()

    report = build_report(args.modal_spend_file)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "merak-plan-completion-audit.json"
    markdown_path = args.output_dir / "merak-plan-completion-audit.md"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")

    summary = report["summary"]
    print(f"wrote {json_path}")
    print(f"wrote {markdown_path}")
    print(
        "merak_plan_completion_audit "
        f"passed={summary['passed']} "
        f"failed={summary['failed']} "
        f"total={summary['total']}"
    )
    return 0 if summary["failed"] == 0 else 1


def build_report(modal_spend_file: Path | None) -> dict[str, Any]:
    eval_report = read_json(REPO_ROOT / "artifacts/merak-plan-eval/merak-plan-eval-report.json")
    reference_submissions = read_json(
        REPO_ROOT / "artifacts/merak-plan-eval/merak-plan-reference-submissions.json"
    )
    demo_eval_report = read_json(
        REPO_ROOT / "artifacts/merak-plan-demo/merak-plan-demo-eval-report.json"
    )
    demo_transcript = read_text(REPO_ROOT / "artifacts/merak-plan-demo/merak-plan-demo.txt")
    modal_snapshot = read_json(modal_spend_file) if modal_spend_file else None

    items = [
        audit_tui_plan_mode(),
        audit_request_user_input_ui(),
        audit_agent_behavior_template(),
        audit_eval_coverage(eval_report),
        audit_question_bound(reference_submissions),
        audit_required_plan_fields(reference_submissions),
        audit_tool_selection(eval_report),
        audit_demo_artifact(demo_eval_report, demo_transcript),
        audit_modal_cleanup_and_spend(modal_spend_file, modal_snapshot),
    ]

    passed = sum(1 for item in items if item.passed)
    failed = len(items) - passed
    return {
        "summary": {
            "passed": passed,
            "failed": failed,
            "total": len(items),
        },
        "items": [item_to_dict(item) for item in items],
        "modal_spend": modal_spend_summary(modal_spend_file, modal_snapshot),
    }


def audit_tui_plan_mode() -> AuditItem:
    files = {
        "protocol": REPO_ROOT / "codex-rs/protocol/src/config_types.rs",
        "settings": REPO_ROOT / "codex-rs/tui/src/chatwidget/settings.rs",
        "composer": REPO_ROOT / "codex-rs/tui/src/bottom_pane/chat_composer.rs",
        "mode_tests": REPO_ROOT / "codex-rs/tui/src/chatwidget/tests/plan_mode.rs",
    }
    checks = {
        "ModeKind::MerakPlan": contains(files["protocol"], "MerakPlan"),
        "visible before traditional Plan": contains(files["protocol"], "ModeKind::MerakPlan, ModeKind::Plan"),
        "nudge names Merak plan mode": contains(files["composer"], "use Merak plan mode"),
        "shift-tab cycle test": contains(
            files["mode_tests"], "plan_mode_nudge_shift_tab_uses_existing_mode_cycle_path"
        ),
    }
    return AuditItem(
        id="tui-plan-mode",
        requirement=(
            "First Shift+Tab enters Merak Plan mode, second enters traditional Plan mode, "
            "and the default nudge returns after cycling."
        ),
        passed=all(checks.values()),
        evidence=tuple(path_label(path) for path in files.values()),
        notes=failed_checks(checks),
    )


def audit_request_user_input_ui() -> AuditItem:
    files = {
        "ui": REPO_ROOT / "codex-rs/tui/src/bottom_pane/request_user_input/mod.rs",
        "recommended_snapshot": REPO_ROOT
        / "codex-rs/tui/src/bottom_pane/request_user_input/snapshots/codex_tui__bottom_pane__request_user_input__tests__request_user_input_recommended_option.snap",
        "summary_snapshot": REPO_ROOT
        / "codex-rs/tui/src/bottom_pane/request_user_input/snapshots/codex_tui__bottom_pane__request_user_input__tests__request_user_input_planning_summary_review.snap",
        "demo_eval": REPO_ROOT / "scripts/merak_plan_demo_eval.py",
    }
    checks = {
        "recommended marker": contains(files["ui"], "Recommended"),
        "recommended snapshot": contains(files["recommended_snapshot"], "Recommended"),
        "planning summary snapshot": contains(files["summary_snapshot"], "planning summary"),
        "demo extracts multi-question plan fields": contains(files["demo_eval"], "KEY_TO_FIELD"),
    }
    return AuditItem(
        id="request-user-input-ui",
        requirement=(
            "TUI supports recommended choices, freeform answers, multi-question flows, "
            "unknown tracking, and planning-summary review."
        ),
        passed=all(checks.values()),
        evidence=tuple(path_label(path) for path in files.values()),
        notes=failed_checks(checks),
    )


def audit_agent_behavior_template() -> AuditItem:
    template = REPO_ROOT / "codex-rs/collaboration-mode-templates/templates/merak_plan.md"
    checks = {
        "decision-changing questions": contains(template, "decision-changing"),
        "discoverable unknowns separated": contains(template, "Discoverable unknowns"),
        "planning summary review": contains(template, "Planning Summary Review"),
        "no mutating implementation": contains(template, "Do not perform mutating implementation"),
        "request_user_input max three": contains(template, "at most three"),
    }
    return AuditItem(
        id="agent-behavior-template",
        requirement="Agent behavior asks only decision-changing questions before planning.",
        passed=all(checks.values()),
        evidence=(path_label(template),),
        notes=failed_checks(checks),
    )


def audit_eval_coverage(eval_report: Any) -> AuditItem:
    required_categories = {
        "UI work",
        "Backend work",
        "Infra work",
        "Repo discovery",
        "Ambiguous goals",
        "Missing credentials",
        "Risky destructive actions",
        "Unclear success metrics",
        "Tool-choice ambiguity",
        "Demo generation",
    }
    categories = {result.get("category") for result in eval_report.get("results", [])}
    summary = eval_report.get("summary", {})
    checks = {
        "ten scenarios": summary.get("total") == 10,
        "all pass": summary.get("passed") == 10 and summary.get("failed") == 0,
        "all required categories": required_categories.issubset(categories),
    }
    return AuditItem(
        id="golden-scenario-evals",
        requirement="Eval harness covers and passes the 10 named golden planning scenarios.",
        passed=all(checks.values()),
        evidence=(
            path_label(REPO_ROOT / "scripts/merak_plan_eval_report.py"),
            path_label(REPO_ROOT / "artifacts/merak-plan-eval/merak-plan-eval-report.json"),
        ),
        notes=failed_checks(checks),
    )


def audit_question_bound(reference_submissions: Any) -> AuditItem:
    counts = {
        str(submission.get("scenario_id")): len(submission.get("question_topics", []))
        for submission in reference_submissions
    }
    too_many = {scenario_id: count for scenario_id, count in counts.items() if count > 3}
    checks = {
        "no scenario above three question topics": not too_many,
        "ten submissions scored": len(counts) == 10,
    }
    return AuditItem(
        id="question-bound",
        requirement="No scenario asks more than three decision-changing questions.",
        passed=all(checks.values()),
        evidence=(path_label(REPO_ROOT / "artifacts/merak-plan-eval/merak-plan-reference-submissions.json"),),
        notes=tuple(f"{scenario_id} has {count} question topics" for scenario_id, count in too_many.items())
        + failed_checks(checks),
    )


def audit_required_plan_fields(reference_submissions: Any) -> AuditItem:
    required_fields = (
        "success_metric",
        "counter_metric",
        "evidence_artifacts",
        "scope_in",
        "scope_out",
        "residual_risks",
    )
    missing: list[str] = []
    for submission in reference_submissions:
        scenario_id = str(submission.get("scenario_id"))
        for field in required_fields:
            value = submission.get(field)
            if not value:
                missing.append(f"{scenario_id} missing {field}")
    return AuditItem(
        id="required-plan-fields",
        requirement=(
            "Every plan includes success metric, counter-metric, evidence artifact, "
            "scope in/out, and residual risks."
        ),
        passed=not missing and len(reference_submissions) == 10,
        evidence=(path_label(REPO_ROOT / "artifacts/merak-plan-eval/merak-plan-reference-submissions.json"),),
        notes=tuple(missing),
    )


def audit_tool_selection(eval_report: Any) -> AuditItem:
    failures = [
        f"{result.get('scenario_id')}: {finding.get('message')}"
        for result in eval_report.get("results", [])
        for finding in result.get("findings", [])
        if "tool" in str(finding.get("code", "")) or "tool" in str(finding.get("message", ""))
    ]
    summary = eval_report.get("summary", {})
    checks = {
        "all evals pass": summary.get("failed") == 0,
        "no tool findings": not failures,
    }
    return AuditItem(
        id="tool-selection",
        requirement="Tool selection is correct in all scenarios according to repo routing rules.",
        passed=all(checks.values()),
        evidence=(
            path_label(REPO_ROOT / "scripts/merak_plan_eval_report.py"),
            path_label(REPO_ROOT / "artifacts/merak-plan-eval/merak-plan-eval-report.json"),
        ),
        notes=tuple(failures) + failed_checks(checks),
    )


def audit_demo_artifact(demo_eval_report: Any, demo_transcript: str) -> AuditItem:
    mp4_path = REPO_ROOT / "artifacts/merak-plan-demo/merak-plan-demo.mp4"
    summary = demo_eval_report.get("summary", {})
    checks = {
        "mp4 exists": mp4_path.exists() and mp4_path.stat().st_size > 0,
        "three demo scenarios pass": summary.get("passed") == 3 and summary.get("failed") == 0,
        "recommended choice shown": "Question type: Recommended choice" in demo_transcript,
        "freeform answer shown": "Question type: Freeform answer" in demo_transcript,
        "multi-question flow shown": "Question type: Multi-question flow" in demo_transcript,
        "codex adapts plan": "Codex adapts the plan" in demo_transcript,
    }
    return AuditItem(
        id="terminal-mp4-demo",
        requirement=(
            "Terminal MP4 demo shows at least three scenarios end-to-end, including user "
            "choice types and Codex adapting the plan."
        ),
        passed=all(checks.values()),
        evidence=(
            path_label(mp4_path),
            path_label(REPO_ROOT / "artifacts/merak-plan-demo/merak-plan-demo.txt"),
            path_label(REPO_ROOT / "artifacts/merak-plan-demo/merak-plan-demo-eval-report.json"),
        ),
        notes=failed_checks(checks),
    )


def audit_modal_cleanup_and_spend(modal_spend_file: Path | None, modal_snapshot: Any) -> AuditItem:
    if modal_spend_file is None:
        return AuditItem(
            id="modal-cleanup-spend",
            requirement="Modal/container work is stopped after runs and spend is reported.",
            passed=False,
            evidence=(),
            notes=("run with --modal-spend-file to attach Modal cleanup and billing evidence",),
        )
    summary = modal_spend_summary(modal_spend_file, modal_snapshot)
    checks = {
        "snapshot readable": summary["snapshot_readable"],
        "active containers zero": summary["active_container_count"] == 0,
        "billing command succeeded": summary["billing_exit_code"] == 0,
        "spend reported": summary["reported_cost_usd"] is not None,
    }
    return AuditItem(
        id="modal-cleanup-spend",
        requirement="Modal/container work is stopped after runs and spend is reported.",
        passed=all(checks.values()),
        evidence=(str(modal_spend_file),),
        notes=failed_checks(checks),
    )


def modal_spend_summary(modal_spend_file: Path | None, modal_snapshot: Any) -> dict[str, Any]:
    if modal_spend_file is None or modal_snapshot is None:
        return {
            "snapshot_path": str(modal_spend_file) if modal_spend_file else None,
            "snapshot_readable": False,
            "active_container_count": None,
            "billing_exit_code": None,
            "reported_cost_usd": None,
        }

    billing = modal_snapshot.get("billing_command", {})
    billing_rows = parse_json_stdout(billing.get("stdout", ""))
    total_cost = sum(Decimal(str(row.get("Cost", "0"))) for row in billing_rows)
    containers = modal_snapshot.get("containers", {})
    return {
        "snapshot_path": str(modal_spend_file),
        "snapshot_readable": True,
        "active_container_count": containers.get("active_count"),
        "billing_exit_code": billing.get("exit_code"),
        "reported_cost_usd": str(total_cost),
        "recorded_at": modal_snapshot.get("recorded_at"),
    }


def parse_json_stdout(stdout: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def read_json(path: Path | None) -> Any:
    if path is None:
        return None
    with path.expanduser().open(encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def contains(path: Path, needle: str) -> bool:
    return path.exists() and needle in path.read_text(encoding="utf-8")


def failed_checks(checks: dict[str, bool]) -> tuple[str, ...]:
    return tuple(f"missing: {name}" for name, passed in checks.items() if not passed)


def item_to_dict(item: AuditItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "requirement": item.requirement,
        "passed": item.passed,
        "evidence": list(item.evidence),
        "notes": list(item.notes),
    }


def path_label(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Merak Plan Completion Audit",
        "",
        f"Passed: {summary['passed']} / {summary['total']}",
        f"Failed: {summary['failed']}",
        "",
        "| Requirement | Status | Evidence | Notes |",
        "| --- | --- | --- | --- |",
    ]
    for item in report["items"]:
        status = "PASS" if item["passed"] else "FAIL"
        evidence = "<br>".join(item["evidence"]) or "-"
        notes = "<br>".join(item["notes"]) or "-"
        lines.append(f"| {item['id']} | {status} | {evidence} | {notes} |")

    modal = report["modal_spend"]
    lines.extend(
        [
            "",
            "## Modal Spend",
            "",
            f"- Snapshot: {modal['snapshot_path'] or '-'}",
            f"- Recorded at: {modal.get('recorded_at') or '-'}",
            f"- Active containers: {modal['active_container_count']}",
            f"- Reported cost USD: {modal['reported_cost_usd']}",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
