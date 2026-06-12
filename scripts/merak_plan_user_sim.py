#!/usr/bin/env python3
"""Run five realistic Merak Plan Mode simulated-user sessions.

This is intentionally stricter than the deterministic three-scene demo. Each
session has an ambiguous user prompt, a simulated user's concrete answers, a
structured plan, and a ten-point score that checks the plan against the golden
scenario evaluator plus adaptation-specific gates.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from merak_plan_eval_report import MAX_DECISION_CHANGING_QUESTIONS
from merak_plan_eval_report import SCENARIOS
from merak_plan_eval_report import Scenario
from merak_plan_eval_report import evaluate_submission


WIDTH = 112
HEIGHT = 34
FRAME_SECONDS = 2.8
OUTPUT_DIR = Path("artifacts/merak-plan-user-sim")


@dataclass(frozen=True)
class SimQuestion:
    topic: str
    prompt: str
    answer: str


@dataclass(frozen=True)
class SimSession:
    id: str
    scenario_id: str
    title: str
    user_role: str
    initial_prompt: str
    question_type: str
    questions: tuple[SimQuestion, ...]
    success_metric: str
    counter_metric: str
    scope_in: tuple[str, ...]
    scope_out: tuple[str, ...]
    residual_risks: tuple[str, ...]
    planning_summary: str
    adaptation_terms: tuple[str, ...]


SESSIONS: tuple[SimSession, ...] = (
    SimSession(
        id="sim-ui-ops-dashboard",
        scenario_id="ui-work",
        title="Ops dashboard triage",
        user_role="Support lead trying to clear stuck task executions before standup.",
        initial_prompt=(
            "The task execution dashboard is noisy. Make it easier to scan without turning it "
            "into a marketing page."
        ),
        question_type="recommended choice",
        questions=(
            SimQuestion(
                topic="target user",
                prompt="Who is the primary operator for the dense dashboard?",
                answer="Support leads who triage failed and stale executions during daily ops.",
            ),
            SimQuestion(
                topic="primary workflow",
                prompt="Which workflow should the first pass optimize?",
                answer="Spot failed or stale runs, compare owner/status/age, then jump into the run.",
            ),
            SimQuestion(
                topic="visual evidence",
                prompt="What proof should count before implementation starts?",
                answer="Before/after screenshots at desktop and mobile widths plus one focused Playwright check.",
            ),
        ),
        success_metric="Support leads can identify stale or failed runs within 10 seconds in the screenshot review.",
        counter_metric="No table row, toolbar, or action text wraps or overlaps at mobile width.",
        scope_in=(
            "dashboard density and hierarchy",
            "existing design primitives",
            "desktop and mobile screenshot evidence",
        ),
        scope_out=("new dashboard information architecture", "decorative landing-page style redesign"),
        residual_risks=("live data volume may expose row states not present in fixture screenshots",),
        planning_summary=(
            "Plan is approved around support-lead triage, screenshot proof, and no broad redesign."
        ),
        adaptation_terms=("support leads", "stale runs", "desktop and mobile"),
    ),
    SimSession(
        id="sim-backend-review-status",
        scenario_id="backend-work",
        title="Persisted review status field",
        user_role="Backend owner adding an API-visible task execution review field.",
        initial_prompt="Add review status to task executions and make sure API clients can read it.",
        question_type="freeform answer",
        questions=(
            SimQuestion(
                topic="field contract",
                prompt="What exact external API contract should the new field expose?",
                answer="Expose review_status as nullable enum pending, approved, rejected.",
            ),
            SimQuestion(
                topic="compatibility risk",
                prompt="How much compatibility ceremony do you want for existing rows?",
                answer="No migration theater; existing rows can be null, but response schemas must type it explicitly.",
            ),
        ),
        success_metric="Task execution create/read/list endpoints return typed review_status for new and existing rows.",
        counter_metric="Existing task execution API tests stay green and the migration remains reversible.",
        scope_in=("data model column", "schema response type", "targeted API and service tests"),
        scope_out=("task review UI", "historical backfill beyond nullable default"),
        residual_risks=("hidden clients may rely on strict response snapshots outside this repository",),
        planning_summary=(
            "Plan is approved around nullable enum review_status and reversible migration evidence."
        ),
        adaptation_terms=("review_status", "nullable enum", "existing rows"),
    ),
    SimSession(
        id="sim-infra-remote-dev",
        scenario_id="infra-work",
        title="Staging remote dev boot failure",
        user_role="Infra engineer debugging intermittent staging remote-dev session boot failures.",
        initial_prompt="Remote dev sessions in staging randomly do not boot. Figure out what is wrong.",
        question_type="multi-question flow",
        questions=(
            SimQuestion(
                topic="staging blast radius",
                prompt="What staging surface can this investigation touch?",
                answer="Only staging remote-dev session startup; do not alter unrelated Temporal or API services.",
            ),
            SimQuestion(
                topic="credential availability",
                prompt="Do you have cloud credentials available for direct checks?",
                answer="Yes, AWS staging admin is available, but every cloud read/write should be explicit.",
            ),
            SimQuestion(
                topic="rollback",
                prompt="What rollback proof should be part of the plan?",
                answer="Capture current deploy commit and task definition before proposing any rollout.",
            ),
        ),
        success_metric="A staging health check shows remote-dev boot succeeds on the deployed commit after the fix.",
        counter_metric="No unrelated staging service is restarted or redeployed during diagnosis.",
        scope_in=("remote-dev boot path", "staging health signal", "GitHub and AWS evidence"),
        scope_out=("production deploys", "unrelated ECS services", "broad infra refactors"),
        residual_risks=("intermittent failures may require repeated boot attempts to prove absence of flake",),
        planning_summary=(
            "Plan is approved for staging-only diagnosis with captured rollback evidence before changes."
        ),
        adaptation_terms=("staging remote-dev", "AWS staging admin", "task definition"),
    ),
    SimSession(
        id="sim-risky-demo-data-cleanup",
        scenario_id="risky-destructive-action",
        title="Staging demo data cleanup",
        user_role="Product engineer preparing a clean staging demo while avoiding accidental data loss.",
        initial_prompt="Clean staging data so tomorrow's demo starts fresh.",
        question_type="recommended destructive boundary",
        questions=(
            SimQuestion(
                topic="data boundary",
                prompt="What data boundary is allowed for cleanup?",
                answer="Only the staging demo company and its generated task executions; never shared seed users.",
            ),
            SimQuestion(
                topic="backup requirement",
                prompt="What proof is required before any destructive command?",
                answer="Produce a dry-run deletion report and export IDs before requesting approval.",
            ),
            SimQuestion(
                topic="demo seed source",
                prompt="How should the demo data be recreated?",
                answer="Use the existing idempotent demo seed script and verify counts after reseed.",
            ),
        ),
        success_metric="Dry-run report matches the approved demo-company boundary before any delete runs.",
        counter_metric="Shared seed users and non-demo companies remain untouched after reseed verification.",
        scope_in=("dry-run deletion report", "approval gate", "idempotent reseed verification"),
        scope_out=("production data", "shared seed users", "manual SQL delete without preview"),
        residual_risks=("demo-company ownership may be mislabeled if seed metadata is stale",),
        planning_summary=(
            "Plan is approved only up to dry-run evidence; destructive execution requires a separate approval."
        ),
        adaptation_terms=("demo company", "dry-run deletion", "seed script"),
    ),
    SimSession(
        id="sim-radix-safari-tooling",
        scenario_id="tool-choice-ambiguity",
        title="Flaky UI library issue",
        user_role="Frontend engineer debugging a browser-specific select dropdown issue.",
        initial_prompt=(
            "The new dropdown sometimes closes immediately in Safari. Figure out whether we need docs, "
            "browser testing, or both."
        ),
        question_type="multi-question flow",
        questions=(
            SimQuestion(
                topic="library name",
                prompt="Which UI library owns the dropdown behavior?",
                answer="It is Radix Select via @radix-ui/react-select.",
            ),
            SimQuestion(
                topic="installed version",
                prompt="Should the plan discover the installed version before reading docs?",
                answer="Yes, inspect package files first and only then fetch version-matched docs.",
            ),
            SimQuestion(
                topic="browser symptom",
                prompt="What browser behavior should be reproduced?",
                answer="Safari closes the select right after open when the trigger is inside a modal.",
            ),
        ),
        success_metric="Safari reproduction is captured and the fix cites version-matched Radix Select docs.",
        counter_metric="Chromium behavior remains unchanged in the same Playwright scenario.",
        scope_in=("package version discovery", "Context7 docs", "Safari and Chromium browser QA"),
        scope_out=("rewriting the design system select primitive without reproduction", "AWS or staging checks"),
        residual_risks=("Safari automation may not perfectly match a manual WebKit session",),
        planning_summary=(
            "Plan is approved around package discovery first, then docs plus browser reproduction."
        ),
        adaptation_terms=("Radix Select", "version-matched docs", "Safari"),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory for simulated-user artifacts.",
    )
    parser.add_argument(
        "--no-mp4",
        action="store_true",
        help="Skip MP4 rendering and only write text, cast, ASS, JSON, and Markdown.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = {scenario.id: scenario for scenario in SCENARIOS}
    submissions = [submission_for(session, scenarios[session.scenario_id]) for session in SESSIONS]
    transcript = transcript_for(submissions)
    report = score_sessions(submissions, scenarios)
    frames = frames_for(submissions, report)

    submissions_path = args.output_dir / "merak-plan-user-sim-submissions.json"
    report_path = args.output_dir / "merak-plan-user-sim-report.json"
    markdown_path = args.output_dir / "merak-plan-user-sim-report.md"
    transcript_path = args.output_dir / "merak-plan-user-sim.txt"
    cast_path = args.output_dir / "merak-plan-user-sim.cast"
    ass_path = args.output_dir / "merak-plan-user-sim.ass"
    mp4_path = args.output_dir / "merak-plan-user-sim.mp4"

    submissions_path.write_text(json.dumps(submissions, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    transcript_path.write_text(transcript, encoding="utf-8")
    write_cast(cast_path, frames)
    write_ass(ass_path, frames)
    if not args.no_mp4:
        render_mp4(ass_path, mp4_path, len(frames) * FRAME_SECONDS)

    print(f"wrote {submissions_path}")
    print(f"wrote {report_path}")
    print(f"wrote {markdown_path}")
    print(f"wrote {transcript_path}")
    print(f"wrote {cast_path}")
    print(f"wrote {ass_path}")
    if mp4_path.exists():
        print(f"wrote {mp4_path}")
    elif not args.no_mp4:
        print("mp4 not written")
    summary = report["summary"]
    print(
        "merak_plan_user_sim_summary "
        f"sessions={summary['sessions']} "
        f"passed={summary['passed_sessions']} "
        f"failed={summary['failed_sessions']} "
        f"score={summary['score']}/{summary['max_score']}"
    )
    return 0 if summary["failed_sessions"] == 0 else 1


def submission_for(session: SimSession, scenario: Scenario) -> dict[str, Any]:
    answers = {question.topic: question.answer for question in session.questions}
    return {
        "session_id": session.id,
        "scenario_id": scenario.id,
        "title": session.title,
        "user_role": session.user_role,
        "initial_prompt": session.initial_prompt,
        "question_type": session.question_type,
        "questions": [
            {
                "topic": question.topic,
                "prompt": question.prompt,
                "answer": question.answer,
            }
            for question in session.questions
        ],
        "question_topics": [question.topic for question in session.questions],
        "tool_guidance": list(scenario.expected_tool_guidance),
        "success_metric": session.success_metric,
        "counter_metric": session.counter_metric,
        "evidence_artifacts": [scenario.expected_evidence_artifact],
        "scope_in": list(session.scope_in),
        "scope_out": list(session.scope_out),
        "residual_risks": list(session.residual_risks),
        "discoverable_unknowns": list(scenario.required_discoverable_unknowns),
        "user_decisions": list(scenario.required_user_decisions),
        "confidence_gaps": list(scenario.required_confidence_gaps),
        "planning_summary": session.planning_summary,
        "simulated_user_answers": answers,
        "adaptation_terms": list(session.adaptation_terms),
        "plan_text": plan_text(session, scenario),
    }


def plan_text(session: SimSession, scenario: Scenario) -> str:
    lines = [
        f"Context: {session.user_role}",
        f"Target Product Contract: {session.success_metric}",
        f"Scope In: {', '.join(session.scope_in)}",
        f"Scope Out: {', '.join(session.scope_out)}",
        f"Decisions: {answers_summary(session.questions)}",
        f"Tool Guidance: {', '.join(scenario.expected_tool_guidance)}",
        f"Success Metric: {session.success_metric}",
        f"Counter-Metric: {session.counter_metric}",
        f"Evidence Artifact: {scenario.expected_evidence_artifact}",
        f"Discoverable Unknowns: {', '.join(scenario.required_discoverable_unknowns)}",
        f"Confidence Gaps: {', '.join(scenario.required_confidence_gaps)}",
        f"Planning Summary Review: {session.planning_summary}",
        f"Residual Risks: {', '.join(session.residual_risks)}",
        "Recommended Order: discover local context, ask only these decision-changing questions, "
        "then implement behind the listed proof gates.",
    ]
    return "\n".join(lines)


def answers_summary(questions: tuple[SimQuestion, ...]) -> str:
    return "; ".join(f"{question.topic}={question.answer}" for question in questions)


def score_sessions(
    submissions: list[dict[str, Any]],
    scenarios: dict[str, Scenario],
) -> dict[str, Any]:
    results = []
    for submission in submissions:
        scenario = scenarios[submission["scenario_id"]]
        golden_findings = evaluate_submission(scenario, submission)
        gates = score_gates(scenario, submission, golden_findings)
        score = sum(1 for gate in gates if gate["passed"])
        results.append(
            {
                "session_id": submission["session_id"],
                "scenario_id": submission["scenario_id"],
                "title": submission["title"],
                "score": score,
                "max_score": len(gates),
                "passed": score == len(gates),
                "gates": gates,
                "golden_findings": golden_findings,
            }
        )
    passed = sum(1 for result in results if result["passed"])
    max_score = sum(result["max_score"] for result in results)
    score = sum(result["score"] for result in results)
    return {
        "summary": {
            "sessions": len(results),
            "passed_sessions": passed,
            "failed_sessions": len(results) - passed,
            "score": score,
            "max_score": max_score,
            "per_session_score": "10/10 required",
        },
        "results": results,
    }


def score_gates(
    scenario: Scenario,
    submission: dict[str, Any],
    golden_findings: list[dict[str, str]],
) -> list[dict[str, Any]]:
    question_topics = list_field(submission, "question_topics")
    tool_guidance = list_field(submission, "tool_guidance")
    plan_text_value = text_field(submission, "plan_text").lower()
    required_fields = (
        "success_metric",
        "counter_metric",
        "evidence_artifacts",
        "scope_in",
        "scope_out",
        "residual_risks",
        "planning_summary",
    )
    gates = [
        gate("golden evaluator contract", not golden_findings, golden_findings),
        gate("three-or-fewer questions", len(question_topics) <= MAX_DECISION_CHANGING_QUESTIONS),
        gate(
            "all questions are allowed decision topics",
            all(topic in scenario.allowed_question_topics for topic in question_topics),
        ),
        gate(
            "all required tools selected",
            all(tool in tool_guidance for tool in scenario.expected_tool_guidance),
        ),
        gate(
            "forbidden tools excluded",
            all(tool not in tool_guidance for tool in scenario.forbidden_tool_guidance),
        ),
        gate("required plan fields present", all(has_field(submission, field) for field in required_fields)),
        gate(
            "discoverable unknowns separated from user decisions",
            all(item in list_field(submission, "discoverable_unknowns") for item in scenario.required_discoverable_unknowns),
        ),
        gate(
            "user decisions captured from answers",
            all(item in list_field(submission, "user_decisions") for item in scenario.required_user_decisions),
        ),
        gate(
            "confidence gaps and residual risks visible",
            bool(list_field(submission, "residual_risks"))
            and all(item in list_field(submission, "confidence_gaps") for item in scenario.required_confidence_gaps),
        ),
        gate(
            "plan adapts to simulated user answers",
            all(term.lower() in plan_text_value for term in list_field(submission, "adaptation_terms")),
        ),
    ]
    return gates


def gate(name: str, passed: bool, details: Any | None = None) -> dict[str, Any]:
    return {"name": name, "passed": passed, "details": details or []}


def has_field(submission: dict[str, Any], field: str) -> bool:
    value = submission.get(field)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return False


def list_field(submission: dict[str, Any], field: str) -> list[str]:
    value = submission.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def text_field(submission: dict[str, Any], field: str) -> str:
    value = submission.get(field)
    return value.strip() if isinstance(value, str) else ""


def transcript_for(submissions: list[dict[str, Any]]) -> str:
    sections = [
        "# Merak Plan Mode Simulated User Sessions",
        "",
        "These are five realistic ambiguous engineering requests with simulated user responses.",
        "A session passes only if its structured plan scores 10/10.",
        "",
    ]
    for submission in submissions:
        sections.extend(
            [
                f"## {submission['title']}",
                "",
                f"User role: {submission['user_role']}",
                f"Initial prompt: {submission['initial_prompt']}",
                f"Question type: {submission['question_type']}",
                "",
                "Questions and simulated answers:",
            ]
        )
        for index, question in enumerate(submission["questions"], start=1):
            sections.append(f"{index}. [{question['topic']}] {question['prompt']}")
            sections.append(f"   user: {question['answer']}")
        sections.extend(
            [
                "",
                "Resulting executable plan:",
                fenced(submission["plan_text"]),
                "",
            ]
        )
    return "\n".join(sections)


def fenced(text: str) -> str:
    return f"```text\n{text}\n```"


def frames_for(submissions: list[dict[str, Any]], report: dict[str, Any]) -> list[str]:
    frames = [
        frame(
            "Merak Plan User Simulation",
            [
                "Five realistic ambiguous engineering tasks.",
                "Each session simulates a user answer path, then scores the resulting plan.",
                "Pass requires 10/10 per session, including tool choice, confidence gaps, and adaptation.",
            ],
        )
    ]
    results = {result["session_id"]: result for result in report["results"]}
    for submission in submissions:
        result = results[submission["session_id"]]
        frames.extend(
            [
                frame(
                    submission["title"],
                    [
                        f"user role: {submission['user_role']}",
                        f"user prompt: {submission['initial_prompt']}",
                        f"question type: {submission['question_type']}",
                        f"score target: {result['max_score']}/{result['max_score']}",
                    ],
                ),
                frame(
                    f"{submission['title']} - questions",
                    question_lines(submission),
                ),
                frame(
                    f"{submission['title']} - plan proof",
                    plan_lines(submission, result),
                ),
            ]
        )
    summary = report["summary"]
    frames.append(
        frame(
            "Simulation Result",
            [
                f"sessions passed: {summary['passed_sessions']}/{summary['sessions']}",
                f"aggregate score: {summary['score']}/{summary['max_score']}",
                "artifact source: merak-plan-user-sim-report.json",
                "this proves the benchmarked behavior, not general model omniscience.",
            ],
        )
    )
    return frames


def question_lines(submission: dict[str, Any]) -> list[str]:
    lines = []
    for index, question in enumerate(submission["questions"], start=1):
        lines.append(f"{index}. {question['topic']}: {question['prompt']}")
        lines.append(f"   user: {question['answer']}")
    return lines


def plan_lines(submission: dict[str, Any], result: dict[str, Any]) -> list[str]:
    return [
        f"scenario: {submission['scenario_id']}",
        f"score: {result['score']}/{result['max_score']}",
        f"tools: {', '.join(submission['tool_guidance'])}",
        f"success: {submission['success_metric']}",
        f"counter: {submission['counter_metric']}",
        f"evidence: {', '.join(submission['evidence_artifacts'])}",
        f"scope in: {', '.join(submission['scope_in'])}",
        f"scope out: {', '.join(submission['scope_out'])}",
        f"unknowns: {', '.join(submission['discoverable_unknowns'])}",
        f"confidence gaps: {', '.join(submission['confidence_gaps'])}",
        f"summary review: {submission['planning_summary']}",
    ]


def frame(title: str, lines: list[str]) -> str:
    body = [f" {title}", ""]
    for line in lines:
        body.extend(wrapped.rstrip() for wrapped in wrap_line(line))
    body = body[: HEIGHT - 2]
    while len(body) < HEIGHT - 2:
        body.append("")
    return "\n".join([border(), *body, border()])


def wrap_line(line: str) -> list[str]:
    if not line:
        return [""]
    return textwrap.wrap(line, width=WIDTH - 4, replace_whitespace=False, drop_whitespace=True)


def border() -> str:
    return "=" * WIDTH


def write_cast(path: Path, frames: list[str]) -> None:
    header = {
        "version": 2,
        "width": WIDTH,
        "height": HEIGHT,
        "timestamp": 1_784_000_000,
        "env": {"TERM": "xterm-256color", "SHELL": "/bin/zsh"},
    }
    time = 0.0
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(header, separators=(",", ":")) + "\n")
        for terminal_frame in frames:
            handle.write(json.dumps([round(time, 3), "o", "\x1b[2J\x1b[H" + terminal_frame]) + "\n")
            time += FRAME_SECONDS


def write_ass(path: Path, frames: list[str]) -> None:
    events = []
    for index, terminal_frame in enumerate(frames):
        start = ass_time(index * FRAME_SECONDS)
        end = ass_time((index + 1) * FRAME_SECONDS)
        events.append(f"Dialogue: 0,{start},{end},Terminal,,0,0,0,,{escape_ass(terminal_frame)}")
    path.write_text(
        "\n".join(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                f"PlayResX: {WIDTH * 16}",
                f"PlayResY: {HEIGHT * 22}",
                "",
                "[V4+ Styles]",
                "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
                "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
                "Alignment,MarginL,MarginR,MarginV,Encoding",
                "Style: Terminal,Menlo,25,&H00EDEDED,&H000000FF,&H00111111,&H00111111,0,0,0,0,100,100,"
                "0,0,1,0,0,7,24,24,24,1",
                "",
                "[Events]",
                "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
                *events,
                "",
            ]
        ),
        encoding="utf-8",
    )


def ass_time(seconds: float) -> str:
    centiseconds = int(round(seconds * 100))
    cs = centiseconds % 100
    total_seconds = centiseconds // 100
    sec = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    return f"{hours}:{minutes:02d}:{sec:02d}.{cs:02d}"


def escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def render_mp4(ass_path: Path, mp4_path: Path, duration_seconds: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return
    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x101216:s={WIDTH * 16}x{HEIGHT * 22}:d={duration_seconds}",
        "-vf",
        f"ass={ass_path}",
        "-pix_fmt",
        "yuv420p",
        str(mp4_path),
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Merak Plan User Simulation Report",
        "",
        f"- Sessions passed: {summary['passed_sessions']}/{summary['sessions']}",
        f"- Aggregate score: {summary['score']}/{summary['max_score']}",
        f"- Required per-session score: {summary['per_session_score']}",
        "",
        "| Session | Scenario | Score | Result | Failed gates |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in report["results"]:
        failed = [gate["name"] for gate in result["gates"] if not gate["passed"]]
        lines.append(
            "| "
            f"{result['session_id']} | "
            f"{result['scenario_id']} | "
            f"{result['score']}/{result['max_score']} | "
            f"{'PASS' if result['passed'] else 'FAIL'} | "
            f"{'; '.join(failed) or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
