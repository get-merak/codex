//! Deterministic evaluation fixtures for Merak Plan Mode planning quality.
//!
//! These fixtures define the benchmark contract before any model output is
//! judged. Runtime eval runners can map free-form model output into
//! `MerakPlanSubmission` and reuse this evaluator.

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum MerakPlanScenarioKind {
    UiWork,
    BackendWork,
    InfraWork,
    RepoDiscovery,
    AmbiguousGoal,
    MissingCredentials,
    RiskyDestructiveAction,
    UnclearSuccessMetrics,
    ToolChoiceAmbiguity,
    DemoGeneration,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum ToolGuidance {
    ReadRepoInstructions,
    GitStatus,
    Ripgrep,
    ReadFiles,
    Context7Docs,
    BrowserQa,
    TargetedTests,
    MigrationCycle,
    AwsStaging,
    ModalSandbox,
    SpendReport,
    GithubChecks,
    NoMutationInPlanMode,
    AskBeforeDestructiveAction,
    StopRemoteWork,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum EvalFindingKind {
    UnknownScenario,
    TooManyQuestions,
    UnexpectedQuestion,
    MissingToolGuidance,
    ForbiddenToolGuidance,
    MissingSuccessMetric,
    MissingCounterMetric,
    MissingEvidenceArtifact,
    MissingScope,
    MissingResidualRisk,
    MissingDiscoverableUnknown,
    MissingUserDecision,
    MissingConfidenceGap,
    MissingPlanningSummary,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EvalFinding {
    pub kind: EvalFindingKind,
    pub detail: String,
}

impl EvalFinding {
    fn new(kind: EvalFindingKind, detail: impl Into<String>) -> Self {
        Self {
            kind,
            detail: detail.into(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MerakPlanScenario {
    pub id: &'static str,
    pub kind: MerakPlanScenarioKind,
    pub prompt: &'static str,
    pub allowed_question_topics: &'static [&'static str],
    pub expected_tool_guidance: &'static [ToolGuidance],
    pub forbidden_tool_guidance: &'static [ToolGuidance],
    pub required_discoverable_unknowns: &'static [&'static str],
    pub required_user_decisions: &'static [&'static str],
    pub required_confidence_gaps: &'static [&'static str],
    pub expected_evidence_artifact: &'static str,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MerakPlanSubmission<'a> {
    pub scenario_id: &'a str,
    pub question_topics: &'a [&'a str],
    pub tool_guidance: &'a [ToolGuidance],
    pub success_metric: Option<&'a str>,
    pub counter_metric: Option<&'a str>,
    pub evidence_artifacts: &'a [&'a str],
    pub scope_in: &'a [&'a str],
    pub scope_out: &'a [&'a str],
    pub residual_risks: &'a [&'a str],
    pub discoverable_unknowns: &'a [&'a str],
    pub user_decisions: &'a [&'a str],
    pub confidence_gaps: &'a [&'a str],
    pub planning_summary: Option<&'a str>,
}

pub const MAX_DECISION_CHANGING_QUESTIONS: usize = 3;

pub fn golden_scenarios() -> &'static [MerakPlanScenario] {
    &GOLDEN_SCENARIOS
}

pub fn evaluate_merak_plan_submission(submission: &MerakPlanSubmission<'_>) -> Vec<EvalFinding> {
    let Some(scenario) = GOLDEN_SCENARIOS
        .iter()
        .find(|scenario| scenario.id == submission.scenario_id)
    else {
        return vec![EvalFinding::new(
            EvalFindingKind::UnknownScenario,
            format!("unknown scenario id {}", submission.scenario_id),
        )];
    };

    let mut findings = Vec::new();

    if submission.question_topics.len() > MAX_DECISION_CHANGING_QUESTIONS {
        findings.push(EvalFinding::new(
            EvalFindingKind::TooManyQuestions,
            format!(
                "asked {} questions; maximum is {MAX_DECISION_CHANGING_QUESTIONS}",
                submission.question_topics.len()
            ),
        ));
    }

    for question_topic in submission.question_topics {
        if !scenario.allowed_question_topics.contains(question_topic) {
            findings.push(EvalFinding::new(
                EvalFindingKind::UnexpectedQuestion,
                format!("unexpected question topic {question_topic}"),
            ));
        }
    }

    for tool in scenario.expected_tool_guidance {
        if !submission.tool_guidance.contains(tool) {
            findings.push(EvalFinding::new(
                EvalFindingKind::MissingToolGuidance,
                format!("missing required tool guidance {tool:?}"),
            ));
        }
    }

    for tool in scenario.forbidden_tool_guidance {
        if submission.tool_guidance.contains(tool) {
            findings.push(EvalFinding::new(
                EvalFindingKind::ForbiddenToolGuidance,
                format!("included forbidden tool guidance {tool:?}"),
            ));
        }
    }

    if submission.success_metric.is_none_or(str::is_empty) {
        findings.push(EvalFinding::new(
            EvalFindingKind::MissingSuccessMetric,
            "missing success metric",
        ));
    }
    if submission.counter_metric.is_none_or(str::is_empty) {
        findings.push(EvalFinding::new(
            EvalFindingKind::MissingCounterMetric,
            "missing counter-metric",
        ));
    }
    if !submission
        .evidence_artifacts
        .contains(&scenario.expected_evidence_artifact)
    {
        findings.push(EvalFinding::new(
            EvalFindingKind::MissingEvidenceArtifact,
            format!(
                "missing expected evidence artifact {}",
                scenario.expected_evidence_artifact
            ),
        ));
    }
    if submission.scope_in.is_empty() || submission.scope_out.is_empty() {
        findings.push(EvalFinding::new(
            EvalFindingKind::MissingScope,
            "scope in/out must both be present",
        ));
    }
    if submission.residual_risks.is_empty() {
        findings.push(EvalFinding::new(
            EvalFindingKind::MissingResidualRisk,
            "missing residual risks",
        ));
    }
    for unknown in scenario.required_discoverable_unknowns {
        if !submission.discoverable_unknowns.contains(unknown) {
            findings.push(EvalFinding::new(
                EvalFindingKind::MissingDiscoverableUnknown,
                format!("missing discoverable unknown {unknown}"),
            ));
        }
    }
    for decision in scenario.required_user_decisions {
        if !submission.user_decisions.contains(decision) {
            findings.push(EvalFinding::new(
                EvalFindingKind::MissingUserDecision,
                format!("missing user decision {decision}"),
            ));
        }
    }
    if submission.planning_summary.is_none_or(str::is_empty) {
        findings.push(EvalFinding::new(
            EvalFindingKind::MissingPlanningSummary,
            "missing planning-summary review",
        ));
    }

    for confidence_gap in scenario.required_confidence_gaps {
        if !submission.confidence_gaps.contains(confidence_gap) {
            findings.push(EvalFinding::new(
                EvalFindingKind::MissingConfidenceGap,
                format!("missing confidence gap {confidence_gap}"),
            ));
        }
    }

    findings
}

const GOLDEN_SCENARIOS: [MerakPlanScenario; 10] = [
    MerakPlanScenario {
        id: "ui-work",
        kind: MerakPlanScenarioKind::UiWork,
        prompt: "Improve an existing dashboard so dense operational data is easier to scan.",
        allowed_question_topics: &["target user", "primary workflow", "visual evidence"],
        expected_tool_guidance: &[
            ToolGuidance::ReadRepoInstructions,
            ToolGuidance::GitStatus,
            ToolGuidance::Ripgrep,
            ToolGuidance::ReadFiles,
            ToolGuidance::BrowserQa,
            ToolGuidance::TargetedTests,
            ToolGuidance::NoMutationInPlanMode,
        ],
        forbidden_tool_guidance: &[ToolGuidance::AwsStaging],
        required_discoverable_unknowns: &[
            "existing design primitives",
            "current viewport behavior",
        ],
        required_user_decisions: &["target user", "primary workflow"],
        required_confidence_gaps: &["design primitive ownership", "viewport evidence"],
        expected_evidence_artifact: "screenshots",
    },
    MerakPlanScenario {
        id: "backend-work",
        kind: MerakPlanScenarioKind::BackendWork,
        prompt: "Add a new API field that is persisted and returned by task execution endpoints.",
        allowed_question_topics: &["field contract", "data lifecycle", "compatibility risk"],
        expected_tool_guidance: &[
            ToolGuidance::ReadRepoInstructions,
            ToolGuidance::GitStatus,
            ToolGuidance::Ripgrep,
            ToolGuidance::ReadFiles,
            ToolGuidance::TargetedTests,
            ToolGuidance::MigrationCycle,
            ToolGuidance::NoMutationInPlanMode,
        ],
        forbidden_tool_guidance: &[ToolGuidance::BrowserQa],
        required_discoverable_unknowns: &["schema owner", "existing migration pattern"],
        required_user_decisions: &["field contract", "compatibility risk"],
        required_confidence_gaps: &["schema owner", "migration reversibility"],
        expected_evidence_artifact: "pytest output",
    },
    MerakPlanScenario {
        id: "infra-work",
        kind: MerakPlanScenarioKind::InfraWork,
        prompt: "Diagnose why staging remote dev sessions sometimes fail to boot.",
        allowed_question_topics: &[
            "staging blast radius",
            "credential availability",
            "rollback",
        ],
        expected_tool_guidance: &[
            ToolGuidance::ReadRepoInstructions,
            ToolGuidance::GitStatus,
            ToolGuidance::Ripgrep,
            ToolGuidance::AwsStaging,
            ToolGuidance::TargetedTests,
            ToolGuidance::GithubChecks,
            ToolGuidance::NoMutationInPlanMode,
        ],
        forbidden_tool_guidance: &[ToolGuidance::AskBeforeDestructiveAction],
        required_discoverable_unknowns: &["current deploy commit", "service health signal"],
        required_user_decisions: &["staging blast radius", "rollback"],
        required_confidence_gaps: &["current deploy commit", "cloud credential scope"],
        expected_evidence_artifact: "staging health check",
    },
    MerakPlanScenario {
        id: "repo-discovery",
        kind: MerakPlanScenarioKind::RepoDiscovery,
        prompt: "Find where notes drag-and-drop is implemented and plan a fix for flaky drops.",
        allowed_question_topics: &["failure symptom", "reproduction path", "success threshold"],
        expected_tool_guidance: &[
            ToolGuidance::ReadRepoInstructions,
            ToolGuidance::GitStatus,
            ToolGuidance::Ripgrep,
            ToolGuidance::ReadFiles,
            ToolGuidance::BrowserQa,
            ToolGuidance::TargetedTests,
            ToolGuidance::NoMutationInPlanMode,
        ],
        forbidden_tool_guidance: &[ToolGuidance::Context7Docs],
        required_discoverable_unknowns: &["canonical drag surface", "existing test coverage"],
        required_user_decisions: &["failure symptom", "success threshold"],
        required_confidence_gaps: &["canonical drag surface", "test flake reproduction"],
        expected_evidence_artifact: "playwright trace",
    },
    MerakPlanScenario {
        id: "ambiguous-goal",
        kind: MerakPlanScenarioKind::AmbiguousGoal,
        prompt: "Make planning feel Claude Code level.",
        allowed_question_topics: &["target behavior", "comparison baseline", "acceptance proof"],
        expected_tool_guidance: &[
            ToolGuidance::ReadRepoInstructions,
            ToolGuidance::GitStatus,
            ToolGuidance::Ripgrep,
            ToolGuidance::ReadFiles,
            ToolGuidance::NoMutationInPlanMode,
        ],
        forbidden_tool_guidance: &[ToolGuidance::AskBeforeDestructiveAction],
        required_discoverable_unknowns: &["current planning prompt", "existing eval coverage"],
        required_user_decisions: &["comparison baseline", "acceptance proof"],
        required_confidence_gaps: &["reference behavior", "quality rubric"],
        expected_evidence_artifact: "eval report",
    },
    MerakPlanScenario {
        id: "missing-credentials",
        kind: MerakPlanScenarioKind::MissingCredentials,
        prompt: "Verify the production deploy succeeded and fix it if not.",
        allowed_question_topics: &["environment target", "credential path", "approval boundary"],
        expected_tool_guidance: &[
            ToolGuidance::ReadRepoInstructions,
            ToolGuidance::GitStatus,
            ToolGuidance::GithubChecks,
            ToolGuidance::NoMutationInPlanMode,
        ],
        forbidden_tool_guidance: &[ToolGuidance::AwsStaging],
        required_discoverable_unknowns: &[
            "available deploy status source",
            "credential availability",
        ],
        required_user_decisions: &["environment target", "approval boundary"],
        required_confidence_gaps: &["credential availability", "production authority"],
        expected_evidence_artifact: "deployment status",
    },
    MerakPlanScenario {
        id: "risky-destructive-action",
        kind: MerakPlanScenarioKind::RiskyDestructiveAction,
        prompt: "Clean up stale staging data so the next demo starts fresh.",
        allowed_question_topics: &["data boundary", "backup requirement", "demo seed source"],
        expected_tool_guidance: &[
            ToolGuidance::ReadRepoInstructions,
            ToolGuidance::GitStatus,
            ToolGuidance::AskBeforeDestructiveAction,
            ToolGuidance::TargetedTests,
            ToolGuidance::NoMutationInPlanMode,
        ],
        forbidden_tool_guidance: &[ToolGuidance::AwsStaging],
        required_discoverable_unknowns: &["destructive scope", "reseed path"],
        required_user_decisions: &["data boundary", "backup requirement"],
        required_confidence_gaps: &["destructive scope", "repeatable reseed path"],
        expected_evidence_artifact: "dry-run deletion report",
    },
    MerakPlanScenario {
        id: "unclear-success-metrics",
        kind: MerakPlanScenarioKind::UnclearSuccessMetrics,
        prompt: "Make task review faster.",
        allowed_question_topics: &["measured workflow", "latency target", "regression limit"],
        expected_tool_guidance: &[
            ToolGuidance::ReadRepoInstructions,
            ToolGuidance::GitStatus,
            ToolGuidance::Ripgrep,
            ToolGuidance::TargetedTests,
            ToolGuidance::NoMutationInPlanMode,
        ],
        forbidden_tool_guidance: &[ToolGuidance::MigrationCycle],
        required_discoverable_unknowns: &["baseline measurement", "current hot path"],
        required_user_decisions: &["latency target", "regression limit"],
        required_confidence_gaps: &["baseline measurement", "counter-metric owner"],
        expected_evidence_artifact: "benchmark output",
    },
    MerakPlanScenario {
        id: "tool-choice-ambiguity",
        kind: MerakPlanScenarioKind::ToolChoiceAmbiguity,
        prompt: "Figure out the right docs and browser tooling for a flaky UI library issue.",
        allowed_question_topics: &["library name", "installed version", "browser symptom"],
        expected_tool_guidance: &[
            ToolGuidance::ReadRepoInstructions,
            ToolGuidance::GitStatus,
            ToolGuidance::Context7Docs,
            ToolGuidance::BrowserQa,
            ToolGuidance::TargetedTests,
            ToolGuidance::NoMutationInPlanMode,
        ],
        forbidden_tool_guidance: &[ToolGuidance::AwsStaging],
        required_discoverable_unknowns: &["library version", "browser reproduction"],
        required_user_decisions: &["library name", "browser symptom"],
        required_confidence_gaps: &["library version", "browser reproduction"],
        expected_evidence_artifact: "doc citation and screenshot",
    },
    MerakPlanScenario {
        id: "demo-generation",
        kind: MerakPlanScenarioKind::DemoGeneration,
        prompt: "Record a terminal MP4 showing three planning scenarios end-to-end.",
        allowed_question_topics: &["demo scenarios", "artifact format", "runtime budget"],
        expected_tool_guidance: &[
            ToolGuidance::ReadRepoInstructions,
            ToolGuidance::GitStatus,
            ToolGuidance::ModalSandbox,
            ToolGuidance::SpendReport,
            ToolGuidance::StopRemoteWork,
            ToolGuidance::NoMutationInPlanMode,
        ],
        forbidden_tool_guidance: &[ToolGuidance::AwsStaging],
        required_discoverable_unknowns: &["recording tool availability", "modal cleanup path"],
        required_user_decisions: &["demo scenarios", "runtime budget"],
        required_confidence_gaps: &["recording tool availability", "scenario coverage"],
        expected_evidence_artifact: "terminal mp4",
    },
];

#[cfg(test)]
#[path = "merak_plan_evals_tests.rs"]
mod tests;
