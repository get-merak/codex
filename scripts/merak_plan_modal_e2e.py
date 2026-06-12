#!/usr/bin/env python3
"""Modal-only end-to-end proof for Merak Plan mode.

Local machine responsibilities:
- read OPENAI_API_KEY from the Merak backend .env without printing it
- upload source to Modal excluding generated/heavy artifacts
- write the returned artifact bundle locally

Modal responsibilities:
- build the Codex fork
- create a realistic dummy repo
- run actual Codex + actual OpenAI model calls
- export transcript, MP4, repos, diff, test output, eval, and cleanup evidence
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

import modal


APP_NAME = "merak-plan-codex-e2e"
LOCAL_REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENV_FILE = Path("/Users/degirmenci/apps/merak/app/.tmp.openai.env")
LOCAL_OUTPUT_DIR = LOCAL_REPO_ROOT / "artifacts/merak-plan-modal-e2e"
REMOTE_SOURCE_ROOT = Path("/workspace/codex-src")
REMOTE_WORK_ROOT = Path("/tmp/merak-plan-e2e")
MODEL = "gpt-5.5"
REASONING_EFFORT = "medium"


def _load_local_openai_api_key() -> str:
    for raw_line in LOCAL_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "OPENAI_API_KEY":
            key = value.strip().strip('"').strip("'")
            if key:
                return key
    raise RuntimeError(f"OPENAI_API_KEY not found in {LOCAL_ENV_FILE}")


image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "build-essential",
        "bubblewrap",
        "ca-certificates",
        "clang",
        "cmake",
        "curl",
        "ffmpeg",
        "git",
        "liblzma-dev",
        "libssl-dev",
        "nodejs",
        "npm",
        "pkg-config",
        "protobuf-compiler",
        "xz-utils",
    )
    .run_commands(
        "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | "
        "sh -s -- -y --profile minimal"
    )
    .env({"PATH": "/root/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"})
    .add_local_dir(
        LOCAL_REPO_ROOT,
        str(REMOTE_SOURCE_ROOT),
        ignore=[
            ".git",
            ".git/**",
            "artifacts",
            "artifacts/**",
            "codex-rs/target",
            "codex-rs/target/**",
            "node_modules",
            "node_modules/**",
            "**/__pycache__",
            "**/__pycache__/**",
            "**/.DS_Store",
        ],
    )
)

app = modal.App(APP_NAME, image=image)


@app.function(
    timeout=7200,
    cpu=4,
    memory=16384,
    ephemeral_disk=524288,
)
def run_e2e(openai_api_key: str) -> bytes:
    transcript: list[str] = []
    started = datetime.now(timezone.utc)
    os.environ["OPENAI_API_KEY"] = openai_api_key
    os.environ["CODEX_API_KEY"] = openai_api_key
    try:
        return _run_e2e_inner(transcript, started)
    except BaseException as exc:
        return _write_failure_bundle(transcript, started, exc)


def _run_e2e_inner(transcript: list[str], started: datetime) -> bytes:
    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError("OPENAI_API_KEY missing in Modal function environment")

    if REMOTE_WORK_ROOT.exists():
        shutil.rmtree(REMOTE_WORK_ROOT)
    source_dir = REMOTE_WORK_ROOT / "codex-src"
    artifact_dir = REMOTE_WORK_ROOT / "artifacts"
    repo_dir = REMOTE_WORK_ROOT / "supportdesk"
    codex_home = REMOTE_WORK_ROOT / "codex-home"
    target_dir = REMOTE_WORK_ROOT / "codex-target"
    source_dir.parent.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(
        REMOTE_SOURCE_ROOT,
        source_dir,
        ignore=shutil.ignore_patterns(".git", "artifacts", "codex-rs/target", "__pycache__"),
    )
    _write_dummy_repo(repo_dir)
    _write_codex_home(codex_home)

    _run(
        ["bash", "-lc", "cargo build -p codex-cli --bin codex"],
        cwd=source_dir / "codex-rs",
        transcript=transcript,
        env=_build_env(target_dir, codex_home),
        timeout=5400,
    )
    codex_bin = target_dir / "debug" / "codex"
    if not codex_bin.exists():
        raise RuntimeError("Codex binary was not produced by remote build")

    _run([str(codex_bin), "--help"], cwd=repo_dir, transcript=transcript, env=_codex_env(codex_home))
    _run([str(codex_bin), "exec", "--help"], cwd=repo_dir, transcript=transcript, env=_codex_env(codex_home))

    before_tar = artifact_dir / "repo-before.tar.gz"
    _tar_path(repo_dir, before_tar)

    prompt_1 = textwrap.dedent(
        """\
        Hey, let's add a better way for support leads to see stale and failed task executions.
        It should be easier to scan and less noisy.

        You are in Merak Plan mode. First turn only:
        - inspect the repo before asking anything
        - do not edit files
        - ask at most three decision-changing clarification questions
        - because this is a non-interactive terminal proof, do not only say you asked questions in the UI
        - your final response must include the exact questions as Q1, Q2, and Q3, each ending with a question mark
        - do not include the implementation plan yet
        - use the new Merak Plan behavior, not vanilla Codex plan mode
        """
    )
    _codex_exec(
        codex_bin,
        repo_dir,
        codex_home,
        transcript,
        prompt_1,
        artifact_dir / "01-clarifying-questions.md",
        merak_plan=True,
        resume=False,
        sandbox="danger-full-access",
    )

    prompt_2 = textwrap.dedent(
        """\
        Simulated user answers:
        - Primary operator: support leads triaging failed and stale task executions before standup.
        - Product contract: show a compact triage list with failed runs and runs stale for 30+ minutes.
        - Implementation preference: reuse existing source modules; avoid a decorative redesign.
        - Proof required: targeted unit tests and a terminal transcript are enough for this dummy repo.

        Produce the final Merak-shaped plan now. Do not edit files yet.
        Start with the heading "Merak Plan".
        Required shape:
        Context -> Target Product Contract -> Scope (In / Out) -> Decisions -> Phase N -> Recommended Order.
        Each phase needs an Implementation Checklist and verifiable Exit Criteria.
        Include success metric, counter-metric, evidence artifact, residual risks, and Planning Summary Review.
        """
    )
    _codex_exec(
        codex_bin,
        repo_dir,
        codex_home,
        transcript,
        prompt_2,
        artifact_dir / "02-final-plan.md",
        merak_plan=True,
        resume=True,
        sandbox="danger-full-access",
    )

    final_plan = (artifact_dir / "02-final-plan.md").read_text(encoding="utf-8")
    prompt_3 = textwrap.dedent(
        f"""\
        The simulated user approves the plan below. Merak Plan mode is complete for planning.
        Execute the approved implementation in this dummy repo only, then run the targeted tests.

        Approved plan:
        {final_plan}

        Constraints:
        - Modify only this dummy repo.
        - Keep the implementation small.
        - Run npm test before reporting done.
        - Final response must separate done, verified, not verified, and residual risk.
        """
    )
    _codex_exec(
        codex_bin,
        repo_dir,
        codex_home,
        transcript,
        prompt_3,
        artifact_dir / "03-execution-report.md",
        merak_plan=False,
        resume=True,
        sandbox="danger-full-access",
    )

    _run(["git", "diff", "--", "."], cwd=repo_dir, transcript=transcript, output_file=artifact_dir / "implementation.diff")
    test_result = _run(
        ["npm", "test"],
        cwd=repo_dir,
        transcript=transcript,
        output_file=artifact_dir / "test-output.txt",
        check=False,
    )
    after_tar = artifact_dir / "repo-after.tar.gz"
    _tar_path(repo_dir, after_tar)
    transcript.append("")
    transcript.append("[modal-cleanup] single function invocation reached artifact export; no detached sandbox was created")
    transcript_path = artifact_dir / "terminal-transcript.txt"
    transcript_path.write_text("\n".join(transcript) + "\n", encoding="utf-8")
    _render_mp4(transcript_path, artifact_dir / "terminal-recording.mp4")
    _write_eval(artifact_dir, repo_dir, started, test_result.returncode)
    _write_cleanup_evidence(artifact_dir, started)

    bundle = REMOTE_WORK_ROOT / "merak-plan-modal-e2e.tar.gz"
    _tar_path(artifact_dir, bundle)
    return bundle.read_bytes()


def _write_failure_bundle(transcript: list[str], started: datetime, exc: BaseException) -> bytes:
    artifact_dir = REMOTE_WORK_ROOT / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    transcript.append("")
    transcript.append(f"[remote-error] {type(exc).__name__}: {_redact(str(exc))}")
    transcript.append("[modal-cleanup] function returned failure artifacts; no detached sandbox was created")
    transcript_path = artifact_dir / "terminal-transcript.txt"
    transcript_path.write_text("\n".join(transcript) + "\n", encoding="utf-8")

    failure_report = {
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "passed": False,
        "failure": _redact(str(exc)),
        "failure_type": type(exc).__name__,
        "checks": {
            "actual_codex_binary_built_in_modal": "cargo build -p codex-cli --bin codex" in "\n".join(transcript),
            "real_openai_call_not_mock": "codex exec" in "\n".join(transcript),
            "merak_plan_mode_visible": "--merak-plan-mode" in "\n".join(transcript),
            "artifacts_returned_on_failure": True,
        },
    }
    (artifact_dir / "evaluation.json").write_text(json.dumps(failure_report, indent=2) + "\n", encoding="utf-8")
    (artifact_dir / "evaluation.md").write_text(
        "# Merak Plan Modal E2E Evaluation\n\n"
        + "- passed: false\n"
        + f"- failure_type: {failure_report['failure_type']}\n"
        + f"- failure: {failure_report['failure']}\n"
        + f"- model: {MODEL}\n"
        + f"- reasoning effort: {REASONING_EFFORT}\n",
        encoding="utf-8",
    )
    _write_cleanup_evidence(artifact_dir, started)
    try:
        _render_mp4(transcript_path, artifact_dir / "terminal-recording.mp4")
    except BaseException as render_exc:
        transcript.append(f"[mp4-render-error] {type(render_exc).__name__}: {_redact(str(render_exc))}")
        transcript_path.write_text("\n".join(transcript) + "\n", encoding="utf-8")

    bundle = REMOTE_WORK_ROOT / "merak-plan-modal-e2e.tar.gz"
    _tar_path(artifact_dir, bundle)
    return bundle.read_bytes()


def _build_env(target_dir: Path, codex_home: Path) -> dict[str, str]:
    env = _codex_env(codex_home)
    env["CARGO_TARGET_DIR"] = str(target_dir)
    env["CARGO_INCREMENTAL"] = "0"
    return env


def _codex_env(codex_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    env["NO_COLOR"] = "1"
    env["TERM"] = "xterm-256color"
    env["PATH"] = "/root/.cargo/bin:" + env.get("PATH", "")
    return env


def _write_codex_home(codex_home: Path) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "config.toml").write_text(
        textwrap.dedent(
            f"""\
            model = "{MODEL}"
            model_provider = "openai"
            model_reasoning_effort = "{REASONING_EFFORT}"
            plan_mode_reasoning_effort = "{REASONING_EFFORT}"
            include_collaboration_mode_instructions = true
            approval_policy = "never"
            sandbox_mode = "workspace-write"
            hide_agent_reasoning = true
            """
        ),
        encoding="utf-8",
    )


def _write_dummy_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "AGENTS.md": textwrap.dedent(
            """\
            Read source and tests before planning. Do not create a landing page.
            Reuse existing task execution modules. Done means npm test passes.
            """
        ),
        "package.json": json.dumps(
            {
                "name": "supportdesk-ops-dashboard",
                "version": "0.1.0",
                "type": "module",
                "scripts": {"test": "node --test"},
            },
            indent=2,
        )
        + "\n",
        "src/executions.js": textwrap.dedent(
            """\
            export const executions = [
              { id: "run_100", owner: "Ava", status: "succeeded", ageMinutes: 4, task: "Sync CRM" },
              { id: "run_101", owner: "Mina", status: "failed", ageMinutes: 12, task: "Invoice export" },
              { id: "run_102", owner: "Omar", status: "running", ageMinutes: 48, task: "Backfill accounts" },
              { id: "run_103", owner: "Lee", status: "queued", ageMinutes: 9, task: "Refresh search index" }
            ];

            export function listExecutions() {
              return executions;
            }
            """
        ),
        "src/dashboard.js": textwrap.dedent(
            """\
            import { listExecutions } from "./executions.js";

            export function renderDashboardRows() {
              return listExecutions().map((execution) => ({
                id: execution.id,
                label: `${execution.task} - ${execution.status}`,
                owner: execution.owner
              }));
            }
            """
        ),
        "test/dashboard.test.js": textwrap.dedent(
            """\
            import test from "node:test";
            import assert from "node:assert/strict";
            import { renderDashboardRows } from "../src/dashboard.js";

            test("renders all execution rows", () => {
              assert.equal(renderDashboardRows().length, 4);
            });
            """
        ),
    }
    for rel_path, contents in files.items():
        path = repo_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    _run_quiet(["git", "init"], cwd=repo_dir)
    _run_quiet(["git", "add", "."], cwd=repo_dir)
    _run_quiet(
        [
            "git",
            "-c",
            "user.name=Merak Modal Demo",
            "-c",
            "user.email=demo@getmerak.com",
            "commit",
            "-m",
            "Initial supportdesk fixture",
        ],
        cwd=repo_dir,
    )


def _codex_exec(
    codex_bin: Path,
    repo_dir: Path,
    codex_home: Path,
    transcript: list[str],
    prompt: str,
    output_file: Path,
    *,
    merak_plan: bool,
    resume: bool,
    sandbox: str,
) -> subprocess.CompletedProcess[str]:
    command = [
        str(codex_bin),
        "exec",
        "--cd",
        str(repo_dir),
        "--skip-git-repo-check",
        "--model",
        MODEL,
        "--sandbox",
        sandbox,
        "--output-last-message",
        str(output_file),
    ]
    if merak_plan:
        command.append("--merak-plan-mode")
    if resume:
        command.extend(["resume", "--last", prompt])
    else:
        command.append(prompt)
    return _run(command, cwd=repo_dir, transcript=transcript, env=_codex_env(codex_home), timeout=900)


def _run(
    command: list[str],
    *,
    cwd: Path,
    transcript: list[str],
    env: dict[str, str] | None = None,
    timeout: int = 300,
    output_file: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    transcript.append(f"$ {_quote_command(command)}")
    print(f"[remote] running: {_quote_command(command[:3])}")
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    elapsed = time.monotonic() - started
    output = _redact(result.stdout)
    transcript.append(output.strip() if output.strip() else "<no stdout>")
    transcript.append(f"[exit={result.returncode} duration={elapsed:.1f}s]")
    transcript.append("")
    if output_file is not None:
        output_file.write_text(output, encoding="utf-8")
    if check and result.returncode != 0:
        output_tail = output[-4000:] if output else "<no stdout>"
        raise RuntimeError(
            "command failed with exit "
            f"{result.returncode}: {_quote_command(command)}\n\n"
            f"output tail:\n{output_tail}"
        )
    return result


def _run_quiet(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def _write_eval(artifact_dir: Path, repo_dir: Path, started: datetime, test_exit_code: int) -> None:
    transcript = (artifact_dir / "terminal-transcript.txt").read_text(encoding="utf-8")
    plan = (artifact_dir / "02-final-plan.md").read_text(encoding="utf-8")
    execution = (artifact_dir / "03-execution-report.md").read_text(encoding="utf-8")
    diff = (artifact_dir / "implementation.diff").read_text(encoding="utf-8")
    questions = (artifact_dir / "01-clarifying-questions.md").read_text(encoding="utf-8")
    lower_transcript = transcript.lower()
    lower_plan = plan.lower()
    lower_execution = execution.lower()
    checks = {
        "actual_codex_binary_built_in_modal": "cargo build -p codex-cli --bin codex" in transcript,
        "real_openai_call_not_mock": (
            "codex exec" in transcript
            and "session id:" in lower_transcript
            and "invalid_api_key" not in lower_transcript
            and "mock llm transcript" not in lower_transcript
        ),
        "merak_plan_mode_visible": "--merak-plan-mode" in transcript
        and ("merak plan" in lower_plan or "merak-shaped plan" in lower_plan),
        "clarifying_questions_before_plan": "?" in questions and "target product contract" not in questions.lower(),
        "plan_shape_present": all(
            token in lower_plan
            for token in ["context", "target product contract", "scope", "decisions", "recommended order"]
        ),
        "approval_before_execution": "approves the plan" in lower_transcript,
        "execution_changed_repo": bool(diff.strip()),
        "tests_pass": test_exit_code == 0,
        "final_report_sections": all(token in lower_execution for token in ["done", "verified", "residual"]),
        "no_secret_leak": not _contains_secret(transcript),
    }
    score = sum(checks.values())
    report = {
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "score": score,
        "max_score": len(checks),
        "passed": score == len(checks),
        "checks": checks,
        "repo_path_in_modal": str(repo_dir),
    }
    (artifact_dir / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (artifact_dir / "evaluation.md").write_text(
        "# Merak Plan Modal E2E Evaluation\n\n"
        + f"- score: {score}/{len(checks)}\n"
        + f"- passed: {report['passed']}\n"
        + f"- model: {MODEL}\n"
        + f"- reasoning effort: {REASONING_EFFORT}\n\n"
        + "\n".join(f"- {name}: {value}" for name, value in checks.items())
        + "\n",
        encoding="utf-8",
    )


def _write_cleanup_evidence(artifact_dir: Path, started: datetime) -> None:
    (artifact_dir / "modal-cleanup-evidence.md").write_text(
        textwrap.dedent(
            f"""\
            # Modal Cleanup Evidence

            - app: {APP_NAME}
            - started_at: {started.isoformat()}
            - artifact_exported_at: {datetime.now(timezone.utc).isoformat()}
            - cleanup_contract: this is a single Modal function invocation; no detached sandbox or server is created.
            - function finally block marker is appended to terminal-transcript.txt before return.
            - local orchestrator must verify no Modal app/container remains after `modal run` exits.
            """
        ),
        encoding="utf-8",
    )


def _tar_path(source: Path, target: Path) -> None:
    with tarfile.open(target, "w:gz") as tar:
        tar.add(source, arcname=source.name)


def _render_mp4(transcript_path: Path, mp4_path: Path) -> None:
    frames = _frames(transcript_path.read_text(encoding="utf-8"))
    ass_path = mp4_path.with_suffix(".ass")
    _write_ass(ass_path, frames)
    duration = max(len(frames) * 1.8, 3.0)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0b0f14:s=1920x1080:d={duration:.1f}",
            "-vf",
            f"ass={ass_path}",
            "-pix_fmt",
            "yuv420p",
            str(mp4_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def _frames(text: str) -> list[str]:
    lines = text.splitlines()
    frames = []
    for end in range(10, len(lines) + 1, 10):
        window = lines[max(0, end - 36) : end]
        frames.append("\n".join(line[:120] for line in window))
    return frames or [text[:1000]]


def _write_ass(path: Path, frames: list[str]) -> None:
    events = []
    for index, frame in enumerate(frames):
        start = _ass_time(index * 1.8)
        end = _ass_time((index + 1) * 1.8)
        events.append(f"Dialogue: 0,{start},{end},Terminal,,0,0,0,,{_escape_ass(frame)}")
    path.write_text(
        "\n".join(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                "PlayResX: 1920",
                "PlayResY: 1080",
                "",
                "[V4+ Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                "Style: Terminal,Menlo,30,&H00F4F6F8,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,42,42,42,1",
                "",
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                *events,
            ]
        ),
        encoding="utf-8",
    )


def _ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def _redact(text: str) -> str:
    text = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-REDACTED", text)
    text = re.sub(r"((?:OPENAI_API_KEY|CODEX_API_KEY)=)[^\\s]+", r"\1REDACTED", text)
    return text


def _contains_secret(text: str) -> bool:
    return bool(
        re.search(r"sk-[A-Za-z0-9_-]{12,}", text)
        or re.search(r"(?:OPENAI_API_KEY|CODEX_API_KEY)=(?!REDACTED)", text)
    )


def _quote_command(command: list[str]) -> str:
    return " ".join(_quote(part) for part in command)


def _quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=,+@%-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


@app.local_entrypoint()
def main(output_dir: str = str(LOCAL_OUTPUT_DIR)) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    bundle_path = output_path / "merak-plan-modal-e2e.tar.gz"
    bundle_bytes = run_e2e.remote(_load_local_openai_api_key())
    bundle_path.write_bytes(bundle_bytes)
    extracted_artifacts = output_path / "artifacts"
    if extracted_artifacts.exists():
        shutil.rmtree(extracted_artifacts)
    with tarfile.open(fileobj=io.BytesIO(bundle_bytes), mode="r:gz") as tar:
        tar.extractall(output_path)
    print(f"wrote {bundle_path}")
    print(f"extracted {extracted_artifacts}")
