#!/usr/bin/env python3
"""Evaluate Merak Plan Mode golden scenario submissions.

By default this writes a reference report that proves the evaluator contract for
all ten scenarios. Pass --submissions with a JSON file to evaluate live model
outputs mapped into the same structured shape.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_DECISION_CHANGING_QUESTIONS = 3


@dataclass(frozen=True)
class Scenario:
    id: str
    category: str
    prompt: str
    allowed_question_topics: tuple[str, ...]
    expected_tool_guidance: tuple[str, ...]
    forbidden_tool_guidance: tuple[str, ...]
    required_discoverable_unknowns: tuple[str, ...]
    required_user_decisions: tuple[str, ...]
    required_confidence_gaps: tuple[str, ...]
    expected_evidence_artifact: str


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        id="ui-work",
        category="UI work",
        prompt="Improve an existing dashboard so dense operational data is easier to scan.",
        allowed_question_topics=("target user", "primary workflow", "visual evidence"),
        expected_tool_guidance=(
            "read_repo_instructions",
            "git_status",
            "ripgrep",
            "read_files",
            "browser_qa",
            "targeted_tests",
            "no_mutation_in_plan_mode",
        ),
        forbidden_tool_guidance=("aws_staging",),
        required_discoverable_unknowns=("existing design primitives", "current viewport behavior"),
        required_user_decisions=("target user", "primary workflow"),
        required_confidence_gaps=("design primitive ownership", "viewport evidence"),
        expected_evidence_artifact="screenshots",
    ),
    Scenario(
        id="backend-work",
        category="Backend work",
        prompt="Add a new API field that is persisted and returned by task execution endpoints.",
        allowed_question_topics=("field contract", "data lifecycle", "compatibility risk"),
        expected_tool_guidance=(
            "read_repo_instructions",
            "git_status",
            "ripgrep",
            "read_files",
            "targeted_tests",
            "migration_cycle",
            "no_mutation_in_plan_mode",
        ),
        forbidden_tool_guidance=("browser_qa",),
        required_discoverable_unknowns=("schema owner", "existing migration pattern"),
        required_user_decisions=("field contract", "compatibility risk"),
        required_confidence_gaps=("schema owner", "migration reversibility"),
        expected_evidence_artifact="pytest output",
    ),
    Scenario(
        id="infra-work",
        category="Infra work",
        prompt="Diagnose why staging remote dev sessions sometimes fail to boot.",
        allowed_question_topics=(
            "staging blast radius",
            "credential availability",
            "rollback",
        ),
        expected_tool_guidance=(
            "read_repo_instructions",
            "git_status",
            "ripgrep",
            "aws_staging",
            "targeted_tests",
            "github_checks",
            "no_mutation_in_plan_mode",
        ),
        forbidden_tool_guidance=("ask_before_destructive_action",),
        required_discoverable_unknowns=("current deploy commit", "service health signal"),
        required_user_decisions=("staging blast radius", "rollback"),
        required_confidence_gaps=("current deploy commit", "cloud credential scope"),
        expected_evidence_artifact="staging health check",
    ),
    Scenario(
        id="repo-discovery",
        category="Repo discovery",
        prompt="Find where notes drag-and-drop is implemented and plan a fix for flaky drops.",
        allowed_question_topics=("failure symptom", "reproduction path", "success threshold"),
        expected_tool_guidance=(
            "read_repo_instructions",
            "git_status",
            "ripgrep",
            "read_files",
            "browser_qa",
            "targeted_tests",
            "no_mutation_in_plan_mode",
        ),
        forbidden_tool_guidance=("context7_docs",),
        required_discoverable_unknowns=("canonical drag surface", "existing test coverage"),
        required_user_decisions=("failure symptom", "success threshold"),
        required_confidence_gaps=("canonical drag surface", "test flake reproduction"),
        expected_evidence_artifact="playwright trace",
    ),
    Scenario(
        id="ambiguous-goal",
        category="Ambiguous goals",
        prompt="Make planning feel Claude Code level.",
        allowed_question_topics=("target behavior", "comparison baseline", "acceptance proof"),
        expected_tool_guidance=(
            "read_repo_instructions",
            "git_status",
            "ripgrep",
            "read_files",
            "no_mutation_in_plan_mode",
        ),
        forbidden_tool_guidance=("ask_before_destructive_action",),
        required_discoverable_unknowns=("current planning prompt", "existing eval coverage"),
        required_user_decisions=("comparison baseline", "acceptance proof"),
        required_confidence_gaps=("reference behavior", "quality rubric"),
        expected_evidence_artifact="eval report",
    ),
    Scenario(
        id="missing-credentials",
        category="Missing credentials",
        prompt="Verify the production deploy succeeded and fix it if not.",
        allowed_question_topics=("environment target", "credential path", "approval boundary"),
        expected_tool_guidance=(
            "read_repo_instructions",
            "git_status",
            "github_checks",
            "no_mutation_in_plan_mode",
        ),
        forbidden_tool_guidance=("aws_staging",),
        required_discoverable_unknowns=("available deploy status source", "credential availability"),
        required_user_decisions=("environment target", "approval boundary"),
        required_confidence_gaps=("credential availability", "production authority"),
        expected_evidence_artifact="deployment status",
    ),
    Scenario(
        id="risky-destructive-action",
        category="Risky destructive actions",
        prompt="Clean up stale staging data so the next demo starts fresh.",
        allowed_question_topics=("data boundary", "backup requirement", "demo seed source"),
        expected_tool_guidance=(
            "read_repo_instructions",
            "git_status",
            "ask_before_destructive_action",
            "targeted_tests",
            "no_mutation_in_plan_mode",
        ),
        forbidden_tool_guidance=("aws_staging",),
        required_discoverable_unknowns=("destructive scope", "reseed path"),
        required_user_decisions=("data boundary", "backup requirement"),
        required_confidence_gaps=("destructive scope", "repeatable reseed path"),
        expected_evidence_artifact="dry-run deletion report",
    ),
    Scenario(
        id="unclear-success-metrics",
        category="Unclear success metrics",
        prompt="Make task review faster.",
        allowed_question_topics=("measured workflow", "latency target", "regression limit"),
        expected_tool_guidance=(
            "read_repo_instructions",
            "git_status",
            "ripgrep",
            "targeted_tests",
            "no_mutation_in_plan_mode",
        ),
        forbidden_tool_guidance=("migration_cycle",),
        required_discoverable_unknowns=("baseline measurement", "current hot path"),
        required_user_decisions=("latency target", "regression limit"),
        required_confidence_gaps=("baseline measurement", "counter-metric owner"),
        expected_evidence_artifact="benchmark output",
    ),
    Scenario(
        id="tool-choice-ambiguity",
        category="Tool-choice ambiguity",
        prompt="Figure out the right docs and browser tooling for a flaky UI library issue.",
        allowed_question_topics=("library name", "installed version", "browser symptom"),
        expected_tool_guidance=(
            "read_repo_instructions",
            "git_status",
            "context7_docs",
            "browser_qa",
            "targeted_tests",
            "no_mutation_in_plan_mode",
        ),
        forbidden_tool_guidance=("aws_staging",),
        required_discoverable_unknowns=("library version", "browser reproduction"),
        required_user_decisions=("library name", "browser symptom"),
        required_confidence_gaps=("library version", "browser reproduction"),
        expected_evidence_artifact="doc citation and screenshot",
    ),
    Scenario(
        id="demo-generation",
        category="Demo generation",
        prompt="Record a terminal MP4 showing three planning scenarios end-to-end.",
        allowed_question_topics=("demo scenarios", "artifact format", "runtime budget"),
        expected_tool_guidance=(
            "read_repo_instructions",
            "git_status",
            "modal_sandbox",
            "spend_report",
            "stop_remote_work",
            "no_mutation_in_plan_mode",
        ),
        forbidden_tool_guidance=("aws_staging",),
        required_discoverable_unknowns=("recording tool availability", "modal cleanup path"),
        required_user_decisions=("demo scenarios", "runtime budget"),
        required_confidence_gaps=("recording tool availability", "scenario coverage"),
        expected_evidence_artifact="terminal mp4",
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--submissions",
        type=Path,
        help="JSON file containing a list of structured scenario submissions.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/merak-plan-eval"),
        help="Directory for the JSON and Markdown reports.",
    )
    parser.add_argument(
        "--write-reference-submissions",
        action="store_true",
        help="Also write the built-in reference submissions JSON.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    submissions = load_submissions(args.submissions)
    report = evaluate_submissions(submissions)

    json_path = output_dir / "merak-plan-eval-report.json"
    markdown_path = output_dir / "merak-plan-eval-report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")

    if args.write_reference_submissions:
        reference_path = output_dir / "merak-plan-reference-submissions.json"
        reference_path.write_text(
            json.dumps(reference_submissions(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {reference_path}")

    print(f"wrote {json_path}")
    print(f"wrote {markdown_path}")
    print(
        "merak_plan_eval_summary "
        f"passed={report['summary']['passed']} "
        f"failed={report['summary']['failed']} "
        f"total={report['summary']['total']}"
    )
    return 0 if report["summary"]["failed"] == 0 else 1


def load_submissions(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return reference_submissions()
    return json.loads(path.read_text(encoding="utf-8"))


def reference_submissions() -> list[dict[str, Any]]:
    return [
        {
            "scenario_id": scenario.id,
            "question_topics": list(scenario.allowed_question_topics),
            "tool_guidance": list(scenario.expected_tool_guidance),
            "success_metric": "measurable success metric",
            "counter_metric": "bounded regression counter-metric",
            "evidence_artifacts": [scenario.expected_evidence_artifact],
            "scope_in": ["requested behavior"],
            "scope_out": ["unrelated redesign"],
            "residual_risks": ["remaining uncertainty after verification"],
            "discoverable_unknowns": list(scenario.required_discoverable_unknowns),
            "user_decisions": list(scenario.required_user_decisions),
            "confidence_gaps": list(scenario.required_confidence_gaps),
            "planning_summary": "summary reviewed before implementation",
        }
        for scenario in SCENARIOS
    ]


def evaluate_submissions(submissions: list[dict[str, Any]]) -> dict[str, Any]:
    scenarios_by_id = {scenario.id: scenario for scenario in SCENARIOS}
    submissions_by_id = {submission.get("scenario_id"): submission for submission in submissions}
    results = []

    for scenario in SCENARIOS:
        submission = submissions_by_id.get(scenario.id)
        if submission is None:
            findings = [finding("missing_submission", f"missing submission for {scenario.id}")]
        else:
            findings = evaluate_submission(scenario, submission)
        results.append(
            {
                "scenario_id": scenario.id,
                "category": scenario.category,
                "prompt": scenario.prompt,
                "passed": not findings,
                "findings": findings,
            }
        )

    for scenario_id in sorted(set(submissions_by_id) - set(scenarios_by_id)):
        results.append(
            {
                "scenario_id": scenario_id,
                "category": "Unknown",
                "prompt": "",
                "passed": False,
                "findings": [finding("unknown_scenario", f"unknown scenario id {scenario_id}")],
            }
        )

    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed
    return {
        "summary": {
            "passed": passed,
            "failed": failed,
            "total": len(results),
            "max_decision_changing_questions": MAX_DECISION_CHANGING_QUESTIONS,
        },
        "results": results,
    }


def evaluate_submission(scenario: Scenario, submission: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    question_topics = list_field(submission, "question_topics")
    tool_guidance = list_field(submission, "tool_guidance")
    evidence_artifacts = list_field(submission, "evidence_artifacts")
    scope_in = list_field(submission, "scope_in")
    scope_out = list_field(submission, "scope_out")
    residual_risks = list_field(submission, "residual_risks")
    discoverable_unknowns = list_field(submission, "discoverable_unknowns")
    user_decisions = list_field(submission, "user_decisions")
    confidence_gaps = list_field(submission, "confidence_gaps")

    if len(question_topics) > MAX_DECISION_CHANGING_QUESTIONS:
        findings.append(
            finding(
                "too_many_questions",
                f"asked {len(question_topics)} questions; maximum is {MAX_DECISION_CHANGING_QUESTIONS}",
            )
        )
    for topic in question_topics:
        if topic not in scenario.allowed_question_topics:
            findings.append(finding("unexpected_question", f"unexpected question topic {topic}"))

    for tool in scenario.expected_tool_guidance:
        if tool not in tool_guidance:
            findings.append(finding("missing_tool_guidance", f"missing required tool {tool}"))
    for tool in scenario.forbidden_tool_guidance:
        if tool in tool_guidance:
            findings.append(finding("forbidden_tool_guidance", f"included forbidden tool {tool}"))

    if not text_field(submission, "success_metric"):
        findings.append(finding("missing_success_metric", "missing success metric"))
    if not text_field(submission, "counter_metric"):
        findings.append(finding("missing_counter_metric", "missing counter-metric"))
    if scenario.expected_evidence_artifact not in evidence_artifacts:
        findings.append(
            finding(
                "missing_evidence_artifact",
                f"missing expected evidence artifact {scenario.expected_evidence_artifact}",
            )
        )
    if not scope_in or not scope_out:
        findings.append(finding("missing_scope", "scope_in and scope_out must both be present"))
    if not residual_risks:
        findings.append(finding("missing_residual_risk", "missing residual risks"))
    for unknown in scenario.required_discoverable_unknowns:
        if unknown not in discoverable_unknowns:
            findings.append(
                finding(
                    "missing_discoverable_unknown",
                    f"missing discoverable unknown {unknown}",
                )
            )
    for decision in scenario.required_user_decisions:
        if decision not in user_decisions:
            findings.append(
                finding("missing_user_decision", f"missing user decision {decision}")
            )
    if not text_field(submission, "planning_summary"):
        findings.append(finding("missing_planning_summary", "missing planning-summary review"))

    for gap in scenario.required_confidence_gaps:
        if gap not in confidence_gaps:
            findings.append(finding("missing_confidence_gap", f"missing confidence gap {gap}"))

    return findings


def list_field(submission: dict[str, Any], name: str) -> list[str]:
    value = submission.get(name)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def text_field(submission: dict[str, Any], name: str) -> str:
    value = submission.get(name)
    if not isinstance(value, str):
        return ""
    return value.strip()


def finding(kind: str, detail: str) -> dict[str, str]:
    return {"kind": kind, "detail": detail}


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Merak Plan Eval Report",
        "",
        f"- Passed: {summary['passed']}/{summary['total']}",
        f"- Failed: {summary['failed']}",
        f"- Max decision-changing questions: {summary['max_decision_changing_questions']}",
        "",
        "| Scenario | Category | Result | Findings |",
        "| --- | --- | --- | --- |",
    ]
    for result in report["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        findings = "; ".join(finding["kind"] for finding in result["findings"]) or "-"
        lines.append(
            f"| {result['scenario_id']} | {result['category']} | {status} | {findings} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
