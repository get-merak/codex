#!/usr/bin/env python3
"""Generate a deterministic terminal-style Merak Plan Mode demo.

The script writes:

- merak-plan-demo.txt: readable transcript
- merak-plan-demo.cast: asciinema v2 event stream
- merak-plan-demo.ass: subtitle script used for MP4 rendering
- merak-plan-demo.mp4: terminal-style video when ffmpeg is available
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path


WIDTH = 96
HEIGHT = 30
FRAME_SECONDS = 2.4


@dataclass(frozen=True)
class DemoScenario:
    title: str
    user_prompt: str
    question_type: str
    question: str
    answer: str
    plan_delta: str
    plan: tuple[str, ...]


SCENARIOS: tuple[DemoScenario, ...] = (
    DemoScenario(
        title="Scenario 1: ambiguous product goal",
        user_prompt="Make planning feel Claude Code level.",
        question_type="Recommended choice",
        question="Choose the comparison baseline.",
        answer="Focused planning benchmark (Recommended)",
        plan_delta="Codex narrows the request into a measurable planning benchmark.",
        plan=(
            "Scenario ID: ambiguous-goal",
            "Question topics: comparison baseline",
            "Tool guidance: read_repo_instructions, git_status, ripgrep, read_files, no_mutation_in_plan_mode",
            "Scope in: Merak Plan mode prompt, eval rubric, focused behavior tests.",
            "Scope out: full TUI redesign, claims outside the benchmark.",
            "Success metric: 10/10 golden scenarios pass required checks.",
            "Counter-metric: no scenario asks more than 3 unnecessary questions.",
            "Evidence artifacts: eval report",
            "Discoverable unknowns: current planning prompt, existing eval coverage",
            "User decisions: comparison baseline, acceptance proof",
            "Confidence gaps: reference behavior, quality rubric",
            "Planning Summary Review: approved with benchmark proof as the handoff gate.",
            "Residual risks: benchmark can overfit without live task replay.",
        ),
    ),
    DemoScenario(
        title="Scenario 2: backend/data change",
        user_prompt="Add a persisted task execution field and return it from the API.",
        question_type="Freeform answer",
        question="What is the external field contract?",
        answer="Expose `review_status` as a nullable enum: pending, approved, rejected.",
        plan_delta="Codex adapts the plan around schema ownership and migration proof.",
        plan=(
            "Scenario ID: backend-work",
            "Question topics: field contract",
            "Tool guidance: read_repo_instructions, git_status, ripgrep, read_files, targeted_tests, migration_cycle, no_mutation_in_plan_mode",
            "Scope in: data model, schema, API response, targeted service tests.",
            "Scope out: unrelated task review UI and historical data backfill ceremony.",
            "Success metric: API returns review_status for new and existing executions.",
            "Counter-metric: migration remains reversible and existing endpoints stay green.",
            "Evidence artifacts: pytest output",
            "Discoverable unknowns: schema owner, existing migration pattern",
            "User decisions: field contract, compatibility risk",
            "Confidence gaps: schema owner, migration reversibility",
            "Planning Summary Review: user confirms API contract before edits start.",
            "Residual risks: hidden clients may depend on response shape.",
        ),
    ),
    DemoScenario(
        title="Scenario 3: demo generation",
        user_prompt="Record a terminal MP4 showing three planning scenarios end-to-end.",
        question_type="Multi-question flow",
        question="Pick scenarios, artifact format, and runtime budget.",
        answer="Use ambiguous goal + backend + demo generation; MP4 plus cast; Modal budget under one focused run.",
        plan_delta="Codex chooses Modal work, records spend, and stops remote containers.",
        plan=(
            "Scenario ID: demo-generation",
            "Question topics: demo scenarios, artifact format, runtime budget",
            "Tool guidance: read_repo_instructions, git_status, modal_sandbox, spend_report, stop_remote_work, no_mutation_in_plan_mode",
            "Scope in: deterministic terminal MP4, cast, transcript, spend evidence.",
            "Scope out: full live TUI redesign and broad model-quality claims.",
            "Success metric: MP4 shows 3 adapted plans and all required plan fields.",
            "Counter-metric: Modal containers end at zero active after generation.",
            "Evidence artifacts: terminal mp4",
            "Discoverable unknowns: recording tool availability, modal cleanup path",
            "User decisions: demo scenarios, runtime budget",
            "Confidence gaps: recording tool availability, scenario coverage",
            "Planning Summary Review: user approves scenarios, format, and cleanup proof.",
            "Residual risks: scripted demo proves UX shape, not live model quality.",
        ),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/merak-plan-demo"),
        help="Directory for generated demo artifacts.",
    )
    parser.add_argument(
        "--no-mp4",
        action="store_true",
        help="Skip ffmpeg MP4 rendering and only write text/cast/ASS artifacts.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    frames = build_frames()
    transcript_path = output_dir / "merak-plan-demo.txt"
    cast_path = output_dir / "merak-plan-demo.cast"
    ass_path = output_dir / "merak-plan-demo.ass"
    mp4_path = output_dir / "merak-plan-demo.mp4"

    write_transcript(transcript_path, frames)
    write_cast(cast_path, frames)
    write_ass(ass_path, frames)

    if not args.no_mp4:
        render_mp4(ass_path, mp4_path, len(frames) * FRAME_SECONDS)

    print(f"wrote {transcript_path}")
    print(f"wrote {cast_path}")
    print(f"wrote {ass_path}")
    if mp4_path.exists():
        print(f"wrote {mp4_path}")
    elif not args.no_mp4:
        print("mp4 not written")
    return 0


def build_frames() -> list[str]:
    frames = [frame("Merak Plan Mode", intro_lines())]
    for index, scenario in enumerate(SCENARIOS, start=1):
        frames.extend(
            [
                frame(
                    scenario.title,
                    [
                        f"$ codex --mode \"Merak Plan\"",
                        f"user> {scenario.user_prompt}",
                        "",
                        "Codex inspects repo instructions and known routing rules before asking.",
                        f"Question type: {scenario.question_type}",
                    ],
                ),
                frame(
                    f"{scenario.title} - question",
                    [
                        "request_user_input",
                        f"  {scenario.question}",
                        f"  user selects: {scenario.answer}",
                        "",
                        scenario.plan_delta,
                    ],
                ),
                frame(
                    f"{scenario.title} - executable plan",
                    list(scenario.plan),
                ),
            ]
        )
        if index != len(SCENARIOS):
            frames.append(frame("Next scenario", ["shift+tab keeps Merak Plan mode active", ""]))
    frames.append(
        frame(
            "Demo complete",
            [
                "Artifacts:",
                "  merak-plan-demo.mp4",
                "  merak-plan-demo.cast",
                "  merak-plan-demo.txt",
                "",
                "Modal cleanup requirement: container list must be empty after generation.",
            ],
        )
    )
    return frames


def intro_lines() -> list[str]:
    return [
        "Goal: ambiguous engineering task -> decision-changing questions -> executable plan.",
        "",
        "Each scenario demonstrates one question type:",
        "  1. Recommended choice",
        "  2. Freeform answer",
        "  3. Multi-question flow",
        "",
        "Every plan includes: success metric, counter-metric, evidence artifact, scope,",
        "discoverable unknowns, user decisions, confidence gaps, and residual risks.",
        "Before handoff, Merak Plan asks for a planning-summary review.",
    ]


def frame(title: str, lines: list[str]) -> str:
    body = [f" {title}", ""]
    for line in lines:
        body.extend(wrapped_line.rstrip() for wrapped_line in wrap_line(line))
    padded = body[: HEIGHT - 2]
    while len(padded) < HEIGHT - 2:
        padded.append("")
    return "\n".join([border(), *padded, border()])


def wrap_line(line: str) -> list[str]:
    if not line:
        return [""]
    return textwrap.wrap(
        line,
        width=WIDTH - 4,
        replace_whitespace=False,
        drop_whitespace=True,
    )


def border() -> str:
    return "=" * WIDTH


def write_transcript(path: Path, frames: list[str]) -> None:
    path.write_text("\n\n".join(frames) + "\n", encoding="utf-8")


def write_cast(path: Path, frames: list[str]) -> None:
    header = {
        "version": 2,
        "width": WIDTH,
        "height": HEIGHT,
        "timestamp": 1_784_000_000,
        "env": {"TERM": "xterm-256color", "SHELL": "/bin/zsh"},
    }
    events: list[list[object]] = []
    time = 0.0
    for terminal_frame in frames:
        events.append([round(time, 3), "o", "\x1b[2J\x1b[H" + terminal_frame])
        time += FRAME_SECONDS
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(header, separators=(",", ":")) + "\n")
        for event in events:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")


def write_ass(path: Path, frames: list[str]) -> None:
    events = []
    for index, terminal_frame in enumerate(frames):
        start = ass_time(index * FRAME_SECONDS)
        end = ass_time((index + 1) * FRAME_SECONDS)
        escaped = escape_ass(terminal_frame)
        events.append(f"Dialogue: 0,{start},{end},Terminal,,0,0,0,,{escaped}")

    path.write_text(
        "\n".join(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                f"PlayResX: {WIDTH * 16}",
                f"PlayResY: {HEIGHT * 24}",
                "",
                "[V4+ Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding",
                "Style: Terminal,DejaVu Sans Mono,28,&H00E7EDF4,&H00E7EDF4,"
                "&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,0,0,7,36,36,30,1",
                "",
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                *events,
                "",
            ]
        ),
        encoding="utf-8",
    )


def render_mp4(ass_path: Path, mp4_path: Path, duration_seconds: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg is required for MP4 output; rerun with --no-mp4 to skip video")

    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x0b0f14:s={WIDTH * 16}x{HEIGHT * 24}:d={duration_seconds}:r=24",
        "-vf",
        f"subtitles={ass_path}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(mp4_path),
    ]
    subprocess.run(command, check=True)


def ass_time(seconds: float) -> str:
    total_centiseconds = round(seconds * 100)
    centiseconds = total_centiseconds % 100
    total_seconds = total_centiseconds // 100
    secs = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def escape_ass(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", "\\N")
    )


if __name__ == "__main__":
    raise SystemExit(main())
