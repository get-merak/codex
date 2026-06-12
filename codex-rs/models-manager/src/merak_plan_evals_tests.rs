use super::*;
use pretty_assertions::assert_eq;
use std::collections::BTreeSet;

#[test]
fn golden_scenarios_cover_required_benchmark_categories() {
    let kinds: BTreeSet<MerakPlanScenarioKind> = golden_scenarios()
        .iter()
        .map(|scenario| scenario.kind)
        .collect();

    assert_eq!(
        kinds,
        BTreeSet::from([
            MerakPlanScenarioKind::UiWork,
            MerakPlanScenarioKind::BackendWork,
            MerakPlanScenarioKind::InfraWork,
            MerakPlanScenarioKind::RepoDiscovery,
            MerakPlanScenarioKind::AmbiguousGoal,
            MerakPlanScenarioKind::MissingCredentials,
            MerakPlanScenarioKind::RiskyDestructiveAction,
            MerakPlanScenarioKind::UnclearSuccessMetrics,
            MerakPlanScenarioKind::ToolChoiceAmbiguity,
            MerakPlanScenarioKind::DemoGeneration,
        ])
    );
    assert_eq!(golden_scenarios().len(), 10);
}

#[test]
fn reference_submissions_pass_all_golden_scenarios() {
    for scenario in golden_scenarios() {
        let submission = reference_submission(scenario);

        assert_eq!(
            evaluate_merak_plan_submission(&submission),
            Vec::<EvalFinding>::new(),
            "scenario {} should pass",
            scenario.id
        );
    }
}

#[test]
fn evaluator_rejects_missing_required_plan_fields() {
    let scenario = &golden_scenarios()[0];
    let submission = MerakPlanSubmission {
        scenario_id: scenario.id,
        question_topics: &[],
        tool_guidance: scenario.expected_tool_guidance,
        success_metric: None,
        counter_metric: None,
        evidence_artifacts: &[],
        scope_in: &[],
        scope_out: &[],
        residual_risks: &[],
        discoverable_unknowns: &[],
        user_decisions: &[],
        confidence_gaps: &[],
        planning_summary: None,
    };

    let finding_kinds: BTreeSet<EvalFindingKind> = evaluate_merak_plan_submission(&submission)
        .into_iter()
        .map(|finding| finding.kind)
        .collect();

    assert_eq!(
        finding_kinds,
        BTreeSet::from([
            EvalFindingKind::MissingSuccessMetric,
            EvalFindingKind::MissingCounterMetric,
            EvalFindingKind::MissingEvidenceArtifact,
            EvalFindingKind::MissingScope,
            EvalFindingKind::MissingResidualRisk,
            EvalFindingKind::MissingDiscoverableUnknown,
            EvalFindingKind::MissingUserDecision,
            EvalFindingKind::MissingConfidenceGap,
            EvalFindingKind::MissingPlanningSummary,
        ])
    );
}

#[test]
fn evaluator_rejects_extra_questions_and_wrong_tools() {
    let scenario = golden_scenarios()
        .iter()
        .find(|scenario| scenario.id == "demo-generation")
        .expect("demo-generation scenario should exist");
    let question_topics = [
        "demo scenarios",
        "artifact format",
        "runtime budget",
        "implementation language",
    ];
    let submission = MerakPlanSubmission {
        scenario_id: scenario.id,
        question_topics: &question_topics,
        tool_guidance: &[ToolGuidance::AwsStaging],
        success_metric: Some("MP4 covers three scenarios"),
        counter_metric: Some("Modal spend stays bounded"),
        evidence_artifacts: &[scenario.expected_evidence_artifact],
        scope_in: &["recording"],
        scope_out: &["full TUI redesign"],
        residual_risks: &["recording codec drift"],
        discoverable_unknowns: scenario.required_discoverable_unknowns,
        user_decisions: scenario.required_user_decisions,
        confidence_gaps: scenario.required_confidence_gaps,
        planning_summary: Some("reviewed against benchmark"),
    };

    let finding_kinds: Vec<EvalFindingKind> = evaluate_merak_plan_submission(&submission)
        .into_iter()
        .map(|finding| finding.kind)
        .collect();

    assert_eq!(
        finding_kinds,
        vec![
            EvalFindingKind::TooManyQuestions,
            EvalFindingKind::UnexpectedQuestion,
            EvalFindingKind::MissingToolGuidance,
            EvalFindingKind::MissingToolGuidance,
            EvalFindingKind::MissingToolGuidance,
            EvalFindingKind::MissingToolGuidance,
            EvalFindingKind::MissingToolGuidance,
            EvalFindingKind::MissingToolGuidance,
            EvalFindingKind::ForbiddenToolGuidance,
        ]
    );
}

fn reference_submission<'a>(scenario: &'a MerakPlanScenario) -> MerakPlanSubmission<'a> {
    MerakPlanSubmission {
        scenario_id: scenario.id,
        question_topics: scenario.allowed_question_topics,
        tool_guidance: scenario.expected_tool_guidance,
        success_metric: Some("measurable success metric"),
        counter_metric: Some("bounded regression counter-metric"),
        evidence_artifacts: std::slice::from_ref(&scenario.expected_evidence_artifact),
        scope_in: &["requested behavior"],
        scope_out: &["unrelated redesign"],
        residual_risks: &["remaining uncertainty after verification"],
        discoverable_unknowns: scenario.required_discoverable_unknowns,
        user_decisions: scenario.required_user_decisions,
        confidence_gaps: scenario.required_confidence_gaps,
        planning_summary: Some("summary reviewed before implementation"),
    }
}
