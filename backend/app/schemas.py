"""Strict API and Gemini assessment schemas.

The detector and severity reports intentionally remain dictionaries produced by
the existing ML modules.  This module validates the additional user context
and the optional, model-generated layer that sits on top of those reports.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Reject unexpected fields so provider output cannot silently drift."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


PolicyCategory = Literal[
    "third_party_liability",
    "comprehensive_package",
    "standalone_own_damage",
    "unknown",
]

PolicyAddOn = Literal[
    "zero_depreciation",
    "engine_protection",
    "consumables_cover",
    "return_to_invoice",
    "roadside_assistance",
    "unknown",
]


class AssessmentContext(StrictModel):
    """Optional, non-secret context supplied with an image assessment."""

    city_or_region: str | None = Field(default=None, max_length=120)
    vehicle_make: str | None = Field(default=None, max_length=120)
    vehicle_model: str | None = Field(default=None, max_length=120)
    vehicle_year: int | None = Field(default=None, ge=1886, le=2100)
    vehicle_variant: str | None = Field(default=None, max_length=160)
    fuel_or_powertrain: str | None = Field(default=None, max_length=80)
    incident_cause: str | None = Field(default=None, max_length=240)
    policy_category: PolicyCategory = "unknown"
    insurer: str | None = Field(default=None, max_length=160)
    policy_add_ons: list[PolicyAddOn] = Field(default_factory=list, max_length=8)
    deductible_inr: float | None = Field(default=None, ge=0, le=100_000_000)
    policy_start_date: date | None = None
    policy_end_date: date | None = None

    @field_validator("deductible_inr")
    @classmethod
    def finite_deductible(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("deductible_inr must be finite")
        return value

    @model_validator(mode="after")
    def validate_policy_dates(self) -> "AssessmentContext":
        if self.policy_start_date and self.policy_end_date and self.policy_end_date < self.policy_start_date:
            raise ValueError("policy_end_date cannot be earlier than policy_start_date")
        return self


class SourceReference(StrictModel):
    """A source that has been explicitly verified by the application owner."""

    title: str = Field(min_length=1, max_length=240)
    url: str = Field(min_length=8, max_length=600)
    note: str = Field(min_length=1, max_length=500)

    @field_validator("url")
    @classmethod
    def https_only(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("source references must use HTTPS")
        return value


class MoneyRange(StrictModel):
    """A non-negative, finite low/high range; null means unavailable."""

    low: float = Field(ge=0)
    high: float = Field(ge=0)

    @field_validator("low", "high")
    @classmethod
    def finite_money(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("money values must be finite")
        return round(float(value), 2)

    @model_validator(mode="after")
    def high_not_below_low(self) -> "MoneyRange":
        if self.high < self.low:
            raise ValueError("high estimate cannot be lower than low estimate")
        return self


CostComponentStatus = Literal["provided", "not_applicable", "unknown"]


class CostComponent(StrictModel):
    """One cost line with an explicit distinction between zero and missing."""

    status: CostComponentStatus
    amount: MoneyRange | None
    basis: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def validate_component_amount(self) -> "CostComponent":
        if self.status == "provided" and self.amount is None:
            raise ValueError("provided cost components require an amount")
        if self.status == "unknown" and self.amount is not None:
            raise ValueError("unknown cost components must not contain an amount")
        if self.status == "not_applicable" and self.amount is not None:
            if self.amount.low != 0 or self.amount.high != 0:
                raise ValueError("not_applicable cost components must be zero or null")
        return self


class GeminiFindingExplanation(StrictModel):
    finding_id: int = Field(ge=0)
    plain_language: str = Field(min_length=1, max_length=1200)
    technical_context: str = Field(min_length=1, max_length=1200)
    confidence_context: str = Field(min_length=1, max_length=800)
    severity_context: str = Field(min_length=1, max_length=800)
    human_review_required: bool
    review_reasons: list[str] = Field(default_factory=list, max_length=12)


class TechnicalGlossaryEntry(StrictModel):
    term: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=800)


class GeminiRepairEstimate(StrictModel):
    finding_id: int = Field(ge=0)
    damage_category: str = Field(min_length=1, max_length=160)
    possible_repair_approach: str = Field(min_length=1, max_length=900)
    approach_is_hypothesis: bool
    estimate_range: MoneyRange | None
    currency: Literal["INR"]
    labor: CostComponent
    parts: CostComponent
    paint_materials: CostComponent
    other_charges: CostComponent
    tax: CostComponent
    pricing_basis: str = Field(min_length=1, max_length=900)
    assumptions: list[str] = Field(default_factory=list, max_length=16)
    missing_information: list[str] = Field(default_factory=list, max_length=16)
    uncertainty: str = Field(min_length=1, max_length=900)
    human_review_required: bool
    human_review_reasons: list[str] = Field(default_factory=list, max_length=16)


class GeminiVehicleEstimateSummary(StrictModel):
    currency: Literal["INR"]
    status: Literal["available", "not_provided", "requires_human_review"]
    low: float | None
    high: float | None
    reason: str = Field(min_length=1, max_length=900)

    @field_validator("low", "high")
    @classmethod
    def finite_total(cls, value: float | None) -> float | None:
        if value is not None:
            if not math.isfinite(value) or value < 0:
                raise ValueError("vehicle totals must be finite and non-negative")
            return round(float(value), 2)
        return value

    @model_validator(mode="after")
    def validate_total_pair(self) -> "GeminiVehicleEstimateSummary":
        if (self.low is None) != (self.high is None):
            raise ValueError("vehicle total low and high must be supplied together")
        if self.low is not None and self.high is not None and self.high < self.low:
            raise ValueError("vehicle total high cannot be below low")
        if self.status == "available" and self.low is None:
            raise ValueError("available vehicle totals require low and high")
        if self.status != "available" and self.low is not None:
            raise ValueError("withheld vehicle totals must not contain low/high values")
        return self


InsuranceGuidanceStatus = Literal[
    "potentially_relevant",
    "policy_review_required",
    "not_covered_under_this_policy_type_in_the_usual_case",
]


class InsuranceFindingGuidance(StrictModel):
    finding_id: int = Field(ge=0)
    status: InsuranceGuidanceStatus
    potential_coverage_category: str = Field(min_length=1, max_length=300)
    conditions: list[str] = Field(default_factory=list, max_length=16)
    policy_questions: list[str] = Field(default_factory=list, max_length=16)
    missing_information: list[str] = Field(default_factory=list, max_length=16)


class InsuranceGuidance(StrictModel):
    policy_category: PolicyCategory
    summary: str = Field(min_length=1, max_length=1400)
    general_coverage_context: str = Field(min_length=1, max_length=1800)
    finding_guidance: list[InsuranceFindingGuidance] = Field(default_factory=list, max_length=100)
    add_on_notes: list[str] = Field(default_factory=list, max_length=16)
    policy_questions: list[str] = Field(default_factory=list, max_length=16)
    source_references: list[SourceReference] = Field(default_factory=list, max_length=8)
    disclaimer: str = Field(min_length=1, max_length=1200)


class GeminiAssessmentResponse(StrictModel):
    """The single structured response requested from Gemini per assessment."""

    summary: str = Field(min_length=1, max_length=2400)
    overall_assessment_status: Literal[
        "preliminary",
        "requires_human_review",
        "insufficient_information",
    ]
    findings_explanations: list[GeminiFindingExplanation] = Field(max_length=100)
    technical_glossary: list[TechnicalGlossaryEntry] = Field(max_length=24)
    repair_estimates: list[GeminiRepairEstimate] = Field(max_length=100)
    vehicle_estimate_summary: GeminiVehicleEstimateSummary
    insurance_guidance: InsuranceGuidance
    recommended_next_steps: list[str] = Field(min_length=1, max_length=20)
    missing_information: list[str] = Field(default_factory=list, max_length=24)
    human_review_required: bool
    limitations: list[str] = Field(min_length=1, max_length=24)
    final_report_narrative: str = Field(min_length=1, max_length=1800)


class GeminiSummaryResponse(StrictModel):
    """Structured narrative generated only after an explicit summary request."""

    summary: str = Field(min_length=1, max_length=2400)
    findings_explanations: list[GeminiFindingExplanation] = Field(max_length=100)
    technical_glossary: list[TechnicalGlossaryEntry] = Field(max_length=24)
    insurance_guidance: InsuranceGuidance
    recommended_next_steps: list[str] = Field(min_length=1, max_length=20)
    limitations: list[str] = Field(min_length=1, max_length=24)
    human_review_required: bool


class GeminiCostResponse(StrictModel):
    """Image-specific repair-scope estimates; totals are computed by the backend."""

    repair_groups: list["GeminiRepairGroup"] = Field(max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=24)


class GeminiRepairGroup(StrictModel):
    group_id: str = Field(pattern=r"^scope-[0-9]+$", max_length=32)
    finding_ids: list[int] = Field(min_length=1, max_length=100)
    scope_summary: str = Field(min_length=1, max_length=500)
    observed_support: str = Field(min_length=1, max_length=900)
    possible_repair_approach: str = Field(min_length=1, max_length=900)
    approach_is_hypothesis: bool
    parts: CostComponent
    labor: CostComponent
    paint_materials: CostComponent
    other_charges: CostComponent
    tax: CostComponent
    estimate_range: MoneyRange | None
    unavailable_reason: str | None = Field(default=None, max_length=900)
    assumptions: list[str] = Field(default_factory=list, max_length=16)
    missing_information: list[str] = Field(default_factory=list, max_length=16)
    pricing_basis: str = Field(min_length=1, max_length=900)
    professional_inspection_required: bool

    @model_validator(mode="after")
    def explain_unavailable_range(self) -> "GeminiRepairGroup":
        if self.estimate_range is None and not self.unavailable_reason:
            raise ValueError("unavailable repair scope requires a specific reason")
        return self


class GeminiCostLine(StrictModel):
    finding_id: int = Field(ge=0)
    damage_category: str = Field(min_length=1, max_length=160)
    observed_support: str = Field(min_length=1, max_length=900)
    possible_repair_approach: str = Field(min_length=1, max_length=900)
    approach_is_hypothesis: bool
    parts: CostComponent
    labor: CostComponent
    paint_materials: CostComponent
    other_charges: CostComponent
    tax: CostComponent
    estimate_range: MoneyRange | None
    unavailable_reason: str | None = Field(default=None, max_length=900)
    assumptions: list[str] = Field(default_factory=list, max_length=16)
    missing_information: list[str] = Field(default_factory=list, max_length=16)
    pricing_basis: str = Field(min_length=1, max_length=900)
    professional_inspection_required: bool

    @model_validator(mode="after")
    def explain_unavailable_range(self) -> "GeminiCostLine":
        if self.estimate_range is None and not self.unavailable_reason:
            raise ValueError("unavailable estimate requires a specific reason")
        return self


class AssessmentCostLine(GeminiCostLine):
    pricing_status: Literal["ai_estimate", "estimate_unavailable"]


class AssessmentRepairGroup(GeminiRepairGroup):
    pricing_status: Literal["ai_estimate", "estimate_unavailable"]


GeminiCostResponse.model_rebuild()


class GeminiDiagnosticResponse(StrictModel):
    ok: Literal[True]
    message: str = Field(min_length=1, max_length=200)


class GeminiCostEnvelope(StrictModel):
    status: Literal["completed", "unavailable", "disabled", "invalid_response"]
    model: str | None
    message: str = Field(min_length=1, max_length=500)
    generated_at: str | None
    pricing_status: Literal["ai_estimate", "estimate_unavailable"]
    verified_market_price: Literal[False] = False
    illustrative_example_only: Literal[False] = False
    currency: Literal["INR"] = "INR"
    findings: list[AssessmentCostLine] = Field(default_factory=list, max_length=100)
    repair_groups: list[AssessmentRepairGroup] = Field(default_factory=list, max_length=100)
    cost_breakdown: dict[str, CostComponent] = Field(default_factory=dict)
    result_schema_version: Literal[2] = 2
    total_status: Literal["available", "partial_subtotal", "estimate_unavailable"]
    vehicle_total: MoneyRange | None
    partial_subtotal: MoneyRange | None
    total_reason: str
    assumptions: list[str] = Field(default_factory=list, max_length=24)
    error_category: str | None = None

    @model_validator(mode="after")
    def validate_totals_and_status(self) -> "GeminiCostEnvelope":
        if self.total_status == "available" and (self.vehicle_total is None or self.partial_subtotal is not None):
            raise ValueError("available total must have one complete vehicle total")
        if self.total_status == "partial_subtotal" and (self.partial_subtotal is None or self.vehicle_total is not None):
            raise ValueError("partial total must have only a partial subtotal")
        if self.total_status == "estimate_unavailable" and (self.vehicle_total is not None or self.partial_subtotal is not None):
            raise ValueError("unavailable total cannot contain a subtotal")
        if self.status != "completed" and self.pricing_status != "estimate_unavailable":
            raise ValueError("failed requests cannot report an AI estimate")
        if self.pricing_status == "estimate_unavailable" and (
            any(item.estimate_range is not None for item in self.findings)
            or any(item.estimate_range is not None for item in self.repair_groups)
        ):
            raise ValueError("priced finding conflicts with unavailable pricing status")
        return self


class GeminiSummaryEnvelope(StrictModel):
    status: Literal["completed", "unavailable", "disabled", "invalid_response"]
    model: str | None
    message: str = Field(min_length=1, max_length=500)
    generated_at: str | None
    summary: dict | None


GeminiStatus = Literal["completed", "disabled", "unavailable", "invalid_response"]


class GeminiAssessmentEnvelope(StrictModel):
    status: GeminiStatus
    model: str | None
    assessment: dict | None
    message: str = Field(min_length=1, max_length=500)
    generated_at: str | None
    fallback_insurance_guidance: InsuranceGuidance


class AssessmentArtifacts(StrictModel):
    source_image_url: str
    annotated_preview_url: str | None
    annotated_preview_available: bool
    pdf_url: str
    expires_at: str
