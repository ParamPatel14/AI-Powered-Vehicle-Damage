"""Educational Indian motor insurance context, independent of paid AI calls."""

from backend.app.schemas import AssessmentContext, InsuranceGuidance, SourceReference

VERIFIED_SOURCES = [SourceReference(
    title="IRDAI Policyholder — Motor Insurance",
    url="https://policyholder.gov.in/motor-insurance",
    note="Verified during implementation on 2026-10-13: general liability/own-damage distinction, add-ons and deductibles. Not an individual policy or claim decision.",
)]

POLICY_EXPLANATIONS = {
    "third_party_liability": "Third-party liability generally addresses covered liability for injury, death or property damage to others, subject to law and policy terms. It does not ordinarily pay for damage to the insured vehicle itself.",
    "comprehensive_package": "A comprehensive/package policy typically combines third-party liability with own-damage cover, subject to policy wording, insured-declared value (IDV), deductibles, exclusions and conditions.",
    "standalone_own_damage": "Standalone own-damage generally covers eligible damage to the insured vehicle under its own-damage terms. Required third-party liability coverage must be considered separately.",
    "unknown": "The policy category is unknown. Check whether there is own-damage cover as well as third-party liability; damage classification alone cannot establish coverage.",
}

ADD_ON_NOTES = [
    "Zero depreciation may reduce depreciation deductions on eligible parts; limits and exclusions depend on the endorsement.",
    "Engine protection may extend specified engine-related protection; an image cannot establish engine or consequential damage.",
    "Consumables cover may include specified consumable expenses for an eligible claim.",
    "Return-to-invoice may apply to specified total-loss or theft situations, subject to conditions; total loss is not established here.",
    "Roadside assistance may provide specified assistance services; it does not establish repair reimbursement or roadworthiness.",
    "Add-ons are not automatically included. These are general educational descriptions, not verified insurer-specific terms.",
]

DISCLAIMER = (
    "General educational guidance only. Actual policy wording, incident cause, dates, exclusions, "
    "deductibles and insurer assessment determine claim handling. This report neither approves nor "
    "denies a claim. Repair estimates are not insurance payouts; out-of-pocket amounts are not calculated."
)


def educational_guidance(context: AssessmentContext, finding_ids: list[int]) -> InsuranceGuidance:
    missing = ["Actual policy wording and endorsements", "Insurer assessment of the incident"]
    if not context.incident_cause:
        missing.append("Incident cause is unknown")
    if not context.policy_add_ons or "unknown" in context.policy_add_ons:
        missing.append("Purchased add-ons are unknown")
    category = context.policy_category
    status = (
        "not_covered_under_this_policy_type_in_the_usual_case" if category == "third_party_liability"
        else "potentially_relevant" if category != "unknown" and context.incident_cause
        else "policy_review_required"
    )
    questions = [
        "Was own-damage cover active on the incident date?",
        "Is this incident cause included, and what exclusions apply?",
        "What deductible, depreciation, IDV limits and purchased add-ons apply?",
        "What notification, survey and repair-authorisation steps does the insurer require?",
    ]
    return InsuranceGuidance(
        policy_category=category,
        summary=POLICY_EXPLANATIONS[category],
        general_coverage_context=" ".join(POLICY_EXPLANATIONS[k] for k in (
            "third_party_liability", "comprehensive_package", "standalone_own_damage"
        )),
        finding_guidance=[dict(
            finding_id=i, status=status,
            potential_coverage_category="Own-damage terms, if purchased and applicable to the incident",
            conditions=["Cause, policy wording, exclusions, deductibles and claim conditions require checking."],
            policy_questions=questions, missing_information=missing,
        ) for i in finding_ids],
        add_on_notes=ADD_ON_NOTES,
        policy_questions=questions,
        source_references=VERIFIED_SOURCES,
        disclaimer=DISCLAIMER,
    )
