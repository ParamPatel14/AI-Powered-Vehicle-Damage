import type { AssessmentContext, AssessmentResponse, HealthResponse } from '../types/assessment';

const configuredBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();

/**
 * During local Vite development an empty base uses the proxy configured in
 * vite.config.ts, which forwards to http://127.0.0.1:8000 without requiring
 * the Python service to enable browser CORS. A deployed build can set the
 * variable to an explicit API origin.
 */
export const API_BASE_URL = configuredBaseUrl || (import.meta.env.DEV ? '' : 'http://127.0.0.1:8000');

export class ApiError extends Error {
  readonly status: number | null;
  readonly payload: unknown;

  constructor(message: string, status: number | null = null, payload: unknown = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function buildUrl(path: string): string {
  if (!API_BASE_URL) return path;
  return `${API_BASE_URL.replace(/\/$/, '')}${path}`;
}

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return buildUrl(path);
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function responseDetail(payload: unknown, fallback: string): string {
  if (isRecord(payload) && typeof payload.detail === 'string') return payload.detail;
  return fallback;
}

async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path), init);
  } catch {
    throw new ApiError(
      'The assessment service could not be reached. Check that the backend is running.',
    );
  }

  const payload = await readJson(response);
  if (!response.ok) {
    throw new ApiError(
      responseDetail(payload, `The service returned HTTP ${response.status}.`),
      response.status,
      payload,
    );
  }
  return payload;
}

function hasObjectFields(value: unknown, fields: string[]): value is JsonRecord {
  return isRecord(value) && fields.every((field) => field in value);
}

export function isAssessmentResponse(value: unknown): value is AssessmentResponse {
  if (!hasObjectFields(value, [
    'assessment_id',
    'status',
    'source_image',
    'detection_report',
    'severity_assessment',
    'repair_cost_estimate',
  ])) {
    return false;
  }

  const detectionReport = value.detection_report;
  const severity = value.severity_assessment;
  const costs = value.repair_cost_estimate;
  const aiCosts = value.ai_cost_estimate;
  const aiSummary = value.ai_summary;

  return (
    typeof value.assessment_id === 'string' &&
    typeof value.status === 'string' &&
    typeof value.source_image === 'string' &&
    hasObjectFields(detectionReport, ['detections', 'image_width', 'image_height']) &&
    Array.isArray(detectionReport.detections) &&
    hasObjectFields(severity, ['detections', 'summary', 'disclaimer']) &&
    Array.isArray(severity.detections) &&
    hasObjectFields(costs, ['estimates', 'summary', 'currency', 'disclaimer']) &&
    Array.isArray(costs.estimates) &&
    (aiCosts === undefined || (hasObjectFields(aiCosts, ['status', 'pricing_status', 'findings', 'total_status', 'vehicle_total', 'partial_subtotal', 'total_reason']) && Array.isArray(aiCosts.findings) && (aiCosts.result_schema_version !== 2 || (Array.isArray(aiCosts.repair_groups) && isRecord(aiCosts.cost_breakdown))))) &&
    (aiSummary === undefined || hasObjectFields(aiSummary, ['status', 'message', 'summary']))
  );
}

export function isHealthResponse(value: unknown): value is HealthResponse {
  return (
    hasObjectFields(value, ['api', 'ready', 'model', 'pricing_configuration']) &&
    typeof value.api === 'string' &&
    typeof value.ready === 'boolean' &&
    hasObjectFields(value.model, ['available', 'error']) &&
    hasObjectFields(value.pricing_configuration, ['available', 'error'])
  );
}

export async function assessImage(file: File, context: AssessmentContext = { policy_category: 'unknown', policy_add_ons: [] }): Promise<AssessmentResponse> {
  const body = new FormData();
  // This field name is part of the existing FastAPI contract.
  body.append('file', file, file.name);
  body.append('assessment_context', JSON.stringify(context));
  const payload = await requestJson('/api/v1/assessments', {
    method: 'POST',
    body,
  });

  if (!isAssessmentResponse(payload)) {
    throw new ApiError('The service returned an unexpected assessment response.');
  }
  return payload;
}

async function assessmentAction(assessmentId: string, action: 'ai-summary' | 'repair-cost'): Promise<AssessmentResponse> {
  const payload = await requestJson(`/api/v1/assessments/${encodeURIComponent(assessmentId)}/${action}`, { method: 'POST' });
  if (!isAssessmentResponse(payload)) throw new ApiError('The service returned an unexpected assessment response.');
  return payload;
}

export const generateAiAssessment = (assessmentId: string) => assessmentAction(assessmentId, 'ai-summary');
export const calculateRepairCost = (assessmentId: string) => assessmentAction(assessmentId, 'repair-cost');

export interface GeminiDiagnosticResult { status: string; category: string; model?: string; message: string }
export async function runGeminiDiagnostic(): Promise<GeminiDiagnosticResult> {
  const payload = await requestJson('/api/v1/gemini/diagnostic', { method: 'POST' });
  if (!hasObjectFields(payload, ['status', 'category', 'message']) || typeof payload.status !== 'string' || typeof payload.category !== 'string' || typeof payload.message !== 'string') {
    throw new ApiError('The service returned an unexpected Gemini diagnostic response.');
  }
  return { status: payload.status, category: payload.category, message: payload.message, ...(typeof payload.model === 'string' ? { model: payload.model } : {}) };
}

export async function getAssessment(assessmentId: string): Promise<AssessmentResponse> {
  const payload = await requestJson(`/api/v1/assessments/${encodeURIComponent(assessmentId)}`);
  if (!isAssessmentResponse(payload)) throw new ApiError('The service returned an unexpected assessment response.');
  return payload;
}

export async function getHealth(): Promise<HealthResponse> {
  const payload = await requestJson('/health');
  if (!isHealthResponse(payload)) {
    throw new ApiError('The service returned an unexpected health response.');
  }
  return payload;
}
