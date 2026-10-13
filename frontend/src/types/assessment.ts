export type Point = [number, number];
export type Polygon = Point[];

export interface NumericRange {
  low: number | null;
  high: number | null;
}

export interface DetectionEvidence {
  detection_id: number;
  class_id: number;
  class_name: string;
  confidence: number | null;
  bbox_xyxy: number[];
  masks_available: boolean;
  mask_area_pixels?: number | null;
  mask_area_percent?: number | null;
  mask_area_scope?: string;
  mask_area_percent_of_image?: number | null;
  component_relative_area_percent?: number | null;
  component_relative_area_available?: boolean;
  polygons_xy: Polygon[];
}

export interface OverlapPair {
  detection_ids: number[];
  bbox_iou?: number | null;
  mask_iou?: number | null;
  same_class?: boolean;
  possible_duplicate_for_review?: boolean;
  human_review_required?: boolean;
  review_reason?: string | null;
}

export interface OverlapDiagnostics {
  method?: string;
  duplicate_review_iou_threshold?: number;
  overlapping_pairs: OverlapPair[];
  possible_duplicate_pair_count?: number;
}

export interface DetectionReport {
  image_path: string;
  image_width: number;
  image_height: number;
  model_name: string;
  inference_device: string;
  image_size: number;
  confidence_threshold: number;
  coordinate_system: string;
  detection_count: number;
  detections: DetectionEvidence[];
  masks_available: boolean;
  overlap_diagnostics: OverlapDiagnostics;
  timestamp_utc: string;
}

export interface InspectionFlag {
  flag: string;
  reason: string;
}

export type PreliminarySeverity = 'minor' | 'moderate' | 'major' | 'undetermined' | string;

export interface SeverityFinding {
  original_evidence: DetectionEvidence;
  preliminary_severity: PreliminarySeverity;
  severity_reasons: string[];
  image_level_mask_area_percent: number | null;
  mask_area_scope: string;
  component_relative_damage_percent: number | null;
  inspection_flags: InspectionFlag[];
  human_review_required: boolean;
  human_review_reasons: string[];
}

export interface SeveritySummary {
  detection_count: number;
  counts_by_severity: Record<string, number>;
  human_review_count: number;
  inspection_flag_count: number;
}

export interface SeverityRules {
  name: string;
  validated: boolean;
  configuration?: Record<string, unknown>;
  interpretation?: string;
}

export interface SeverityAssessment {
  report_type: string;
  assessment_status: string;
  source_image: string | null;
  source_detection_file: string | null;
  source_image_dimensions: { width: number; height: number };
  detections: SeverityFinding[];
  overlap_pairs: OverlapPair[];
  summary: SeveritySummary;
  rules: SeverityRules;
  disclaimer: string;
  timestamp_utc: string;
}

export interface CalculationItem {
  applicable?: boolean;
  enabled?: boolean;
  description?: string;
  category?: string;
  hourly_rate_range?: NumericRange;
  estimated_hours_range?: NumericRange;
  cost_range?: NumericRange;
  formula?: string;
  rate?: number;
  applies_to?: string[];
  taxable_amount_range?: NumericRange;
}

export interface CostCalculation {
  labor?: CalculationItem;
  parts?: CalculationItem;
  paint_materials?: CalculationItem;
  miscellaneous?: CalculationItem;
  pre_tax_subtotal?: NumericRange;
  tax?: CalculationItem;
  total_cost_range?: NumericRange;
}

export interface CostAssumptions {
  scenario_name: string;
  action_assumption: string;
  vehicle_component: string;
  repair_method_confirmed: boolean;
  repair_method_uncertain: boolean;
  severity_is_provisional: boolean;
  overlap_may_duplicate_cost: boolean;
}

export interface CostEstimate {
  currency: string;
  estimate_type: string;
  estimate_range: NumericRange;
  calculation: CostCalculation;
  assumptions: CostAssumptions;
  human_review_required: boolean;
  human_review_reasons: string[];
  eligible_for_vehicle_total: boolean;
}

export type EstimateStatus = 'conditional_estimate_available' | 'not_estimated' | string;

export interface CostFinding {
  detection_id: number;
  damage_class: string | null;
  preliminary_severity: PreliminarySeverity;
  original_evidence: DetectionEvidence | null;
  estimate_status: EstimateStatus;
  cost_estimate: CostEstimate | null;
  human_review_required: boolean;
  human_review_reasons: string[];
}

export interface VehicleTotal {
  currency: string;
  status: string;
  low: number | null;
  high: number | null;
  human_review_required: boolean;
  reasons: string[];
}

export interface CostSummary {
  detection_count: number;
  counts: {
    conditional_estimate_available: number;
    not_estimated: number;
    human_review_required: number;
    overlap_review: number;
  };
  vehicle_total: VehicleTotal;
}

export interface RepairCostEstimate {
  report_type: string;
  source_image: string | null;
  source_severity_file: string | null;
  pricing_file: string | null;
  pricing_status: string | null;
  currency: string;
  source_severity_status: string | null;
  estimates: CostFinding[];
  summary: CostSummary;
  pricing_source_note: string;
  disclaimer: string;
  timestamp_utc: string;
}

export type PolicyCategory = 'third_party_liability' | 'comprehensive_package' | 'standalone_own_damage' | 'unknown';
export type PolicyAddOn = 'zero_depreciation' | 'engine_protection' | 'consumables_cover' | 'return_to_invoice' | 'roadside_assistance' | 'unknown';

export interface AssessmentContext {
  city_or_region?: string | null;
  vehicle_make?: string | null;
  vehicle_model?: string | null;
  vehicle_year?: number | null;
  vehicle_variant?: string | null;
  fuel_or_powertrain?: string | null;
  incident_cause?: string | null;
  policy_category: PolicyCategory;
  insurer?: string | null;
  policy_add_ons: PolicyAddOn[];
  deductible_inr?: number | null;
  policy_start_date?: string | null;
  policy_end_date?: string | null;
}

export interface AiCostComponent {
  status: 'provided' | 'not_applicable' | 'unknown';
  amount: NumericRange | null;
  basis: string;
}

export interface AiRepairEstimate {
  finding_id: number;
  damage_category: string;
  possible_repair_approach: string;
  approach_is_hypothesis: boolean;
  estimate_range: NumericRange | null;
  validated_estimate_range?: NumericRange | null;
  currency: 'INR';
  labor: AiCostComponent;
  parts: AiCostComponent;
  paint_materials: AiCostComponent;
  other_charges: AiCostComponent;
  tax: AiCostComponent;
  pricing_basis: string;
  pricing_source?: string;
  calculation_scope?: string;
  assumptions: string[];
  missing_information: string[];
  uncertainty: string;
  human_review_required: boolean;
  human_review_reasons: string[];
}

export interface AiFindingExplanation {
  finding_id: number;
  plain_language: string;
  technical_context: string;
  confidence_context: string;
  severity_context: string;
  human_review_required: boolean;
  review_reasons: string[];
}

export interface TechnicalGlossaryEntry {
  term: string;
  explanation: string;
}

export type InsuranceGuidanceStatus = 'potentially_relevant' | 'policy_review_required' | 'not_covered_under_this_policy_type_in_the_usual_case';

export interface InsuranceFindingGuidance {
  finding_id: number;
  status: InsuranceGuidanceStatus;
  potential_coverage_category: string;
  conditions: string[];
  policy_questions: string[];
  missing_information: string[];
}

export interface SourceReference {
  title: string;
  url: string;
  note: string;
}

export interface InsuranceGuidance {
  policy_category: PolicyCategory;
  summary: string;
  general_coverage_context: string;
  finding_guidance: InsuranceFindingGuidance[];
  add_on_notes: string[];
  policy_questions: string[];
  source_references: SourceReference[];
  disclaimer: string;
}

export interface AiVehicleEstimateSummary {
  currency: 'INR';
  status: 'available' | 'not_provided' | 'requires_human_review';
  low: number | null;
  high: number | null;
  reason: string;
}

export interface GeminiAssessment {
  summary: string;
  overall_assessment_status: 'preliminary' | 'requires_human_review' | 'insufficient_information';
  findings_explanations: AiFindingExplanation[];
  technical_glossary: TechnicalGlossaryEntry[];
  repair_estimates: AiRepairEstimate[];
  vehicle_estimate_summary: AiVehicleEstimateSummary;
  insurance_guidance: InsuranceGuidance;
  recommended_next_steps: string[];
  missing_information: string[];
  human_review_required: boolean;
  limitations: string[];
  final_report_narrative: string;
}

export type GeminiStatus = 'completed' | 'disabled' | 'unavailable' | 'invalid_response';

export interface GeminiAssessmentEnvelope {
  status: GeminiStatus;
  model: string | null;
  assessment: GeminiAssessment | null;
  message: string;
  generated_at: string | null;
  fallback_insurance_guidance: InsuranceGuidance;
}

export interface AiSummaryResult {
  status: 'completed' | 'unavailable' | 'disabled' | 'invalid_response';
  model: string | null;
  message: string;
  generated_at: string | null;
  summary: {
    summary: string;
    findings_explanations: AiFindingExplanation[];
    technical_glossary: TechnicalGlossaryEntry[];
    insurance_guidance: InsuranceGuidance;
    recommended_next_steps: string[];
    limitations: string[];
    human_review_required: boolean;
  } | null;
}

export interface AiCostFinding {
  finding_id: number;
  damage_category: string;
  observed_support: string;
  possible_repair_approach: string;
  approach_is_hypothesis: boolean;
  parts: AiCostComponent;
  labor: AiCostComponent;
  paint_materials: AiCostComponent;
  other_charges: AiCostComponent;
  tax: AiCostComponent;
  estimate_range: NumericRange | null;
  unavailable_reason: string | null;
  assumptions: string[];
  missing_information: string[];
  pricing_basis: string;
  professional_inspection_required: boolean;
  pricing_status: 'ai_estimate' | 'estimate_unavailable';
}

export interface AiRepairGroup {
  group_id: string;
  finding_ids: number[];
  scope_summary: string;
  observed_support: string;
  possible_repair_approach: string;
  approach_is_hypothesis: boolean;
  parts: AiCostComponent;
  labor: AiCostComponent;
  paint_materials: AiCostComponent;
  other_charges: AiCostComponent;
  tax: AiCostComponent;
  estimate_range: NumericRange | null;
  unavailable_reason: string | null;
  assumptions: string[];
  missing_information: string[];
  pricing_basis: string;
  professional_inspection_required: boolean;
  pricing_status: 'ai_estimate' | 'estimate_unavailable';
}

export interface AiCostResult {
  status: 'completed' | 'unavailable' | 'disabled' | 'invalid_response';
  model: string | null;
  message: string;
  generated_at: string | null;
  pricing_status: 'ai_estimate' | 'estimate_unavailable';
  verified_market_price: false;
  illustrative_example_only: false;
  currency: 'INR';
  findings: AiCostFinding[];
  repair_groups?: AiRepairGroup[];
  cost_breakdown?: Record<string, AiCostComponent>;
  result_schema_version?: 2;
  total_status: 'available' | 'partial_subtotal' | 'estimate_unavailable';
  vehicle_total: NumericRange | null;
  partial_subtotal: NumericRange | null;
  total_reason: string;
  assumptions: string[];
  error_category?: string;
}

export interface AssessmentArtifacts {
  source_image_url: string;
  annotated_preview_url: string | null;
  annotated_preview_available: boolean;
  pdf_url: string;
  expires_at: string;
}

export interface AssessmentResponse {
  assessment_id: string;
  status: string;
  source_image: string;
  detection_report: DetectionReport;
  severity_assessment: SeverityAssessment;
  repair_cost_estimate: RepairCostEstimate;
  assessment_context?: AssessmentContext;
  gemini_assessment?: GeminiAssessmentEnvelope;
  ai_summary?: AiSummaryResult;
  ai_cost_estimate?: AiCostResult;
  artifacts?: AssessmentArtifacts;
  preliminary?: boolean;
  gemini_status?: { status: 'disabled' | 'configured' | 'unavailable'; model: string | null; image_transmission: boolean; maximum_generation_attempts: number };
  artifact_created_at?: string;
}

export interface AssessmentRecord {
  response: AssessmentResponse;
  previewUrl: string;
  fileName: string;
  fileSize: number;
  createdAt: string;
  sourceImageUrl?: string;
  annotatedPreviewUrl?: string;
  pdfUrl?: string;
}

export interface HealthComponent {
  available: boolean;
  error: string | null;
}

export interface HealthResponse {
  api: string;
  ready: boolean;
  model: HealthComponent;
  pricing_configuration: HealthComponent;
  gemini?: {
    status: 'disabled' | 'configured' | 'unavailable';
    model: string | null;
    image_transmission: boolean;
    image_transmission_mode?: string;
    maximum_generation_attempts: number;
  };
}
