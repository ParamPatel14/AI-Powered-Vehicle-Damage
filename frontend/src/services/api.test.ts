import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, assessImage, calculateRepairCost, generateAiAssessment, getHealth, isAssessmentResponse, runGeminiDiagnostic } from './api';

const responseFixture = {
  assessment_id: 'assessment-123',
  status: 'completed_with_human_review',
  source_image: 'vehicle.png',
  detection_report: {
    image_width: 100,
    image_height: 80,
    detections: [],
  },
  severity_assessment: {
    detections: [],
    summary: {},
    disclaimer: 'Preliminary.',
  },
  repair_cost_estimate: {
    estimates: [],
    summary: {},
    currency: 'USD',
    disclaimer: 'Conditional.',
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('assessment API service', () => {
  it('recognizes the real top-level assessment response shape', () => {
    expect(isAssessmentResponse(responseFixture)).toBe(true);
    expect(isAssessmentResponse({ ...responseFixture, repair_cost_estimate: null })).toBe(false);
  });

  it('posts the image under the backend contract field name', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(responseFixture), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);
    const image = new File(['image'], 'vehicle.png', { type: 'image/png' });

    await expect(assessImage(image)).resolves.toEqual(responseFixture);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect((init.body as FormData).get('file')).toBeInstanceOf(File);
  });

  it('uses the existing assessment id for explicit AI and cost actions without uploading again', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(responseFixture), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);
    await generateAiAssessment('assessment-123');
    await calculateRepairCost('assessment-123');
    expect(fetchMock.mock.calls.map(([url, init]) => [url, (init as RequestInit).method])).toEqual([
      ['/api/v1/assessments/assessment-123/ai-summary', 'POST'],
      ['/api/v1/assessments/assessment-123/repair-cost', 'POST'],
    ]);
  });

  it('serializes optional vehicle and policy context without exposing credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(responseFixture), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const context = {
      city_or_region: 'Pune',
      vehicle_make: 'Tata',
      vehicle_model: 'Nexon',
      policy_category: 'comprehensive_package' as const,
      policy_add_ons: ['zero_depreciation' as const],
      incident_cause: 'Parking impact',
    };

    await assessImage(new File(['image'], 'vehicle.png', { type: 'image/png' }), context);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse((init.body as FormData).get('assessment_context') as string)).toEqual(context);
    expect(JSON.stringify(init.body)).not.toContain('GEMINI_API_KEY');
  });

  it('surfaces backend HTTP errors without hiding the detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Image is malformed.' }), { status: 422 })));

    await expect(assessImage(new File(['image'], 'vehicle.png', { type: 'image/png' }))).rejects.toMatchObject({
      name: 'ApiError',
      status: 422,
      message: 'Image is malformed.',
    } satisfies Partial<ApiError>);
  });

  it('preserves a structured health payload when the service is reachable but unready', async () => {
    const health = {
      api: 'running',
      ready: false,
      model: { available: false, error: 'model_file_missing' },
      pricing_configuration: { available: true, error: null },
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(health), { status: 503 })));

    await expect(getHealth()).rejects.toMatchObject({ status: 503, payload: health });
  });

  it('does not carry an earlier cost estimate into a newly uploaded assessment response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(responseFixture), { status: 200 })));
    const created = await assessImage(new File(['new image'], 'new-car.png', { type: 'image/png' }));
    expect(created.ai_cost_estimate).toBeUndefined();
  });

  it('passes distinct persisted AI costs through without replacing them with examples', async () => {
    const first = { ...responseFixture, ai_cost_estimate: { status: 'completed', pricing_status: 'ai_estimate', findings: [], total_status: 'available', vehicle_total: { low: 12000, high: 18000 }, partial_subtotal: null, total_reason: 'Image-supported conditional total.' } };
    const second = { ...responseFixture, ai_cost_estimate: { status: 'completed', pricing_status: 'ai_estimate', findings: [], total_status: 'available', vehicle_total: { low: 41000, high: 57000 }, partial_subtotal: null, total_reason: 'Different damage evidence.' } };
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(first), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(second), { status: 200 })));
    const a = await calculateRepairCost('assessment-a');
    const b = await calculateRepairCost('assessment-b');
    expect(a.ai_cost_estimate?.vehicle_total?.low).toBe(12000);
    expect(b.ai_cost_estimate?.vehicle_total?.low).toBe(41000);
  });

  it('preserves the consolidated repair scope and one itemized breakdown from the backend', async () => {
    const grouped = {
      ...responseFixture,
      ai_cost_estimate: {
        status: 'completed', pricing_status: 'ai_estimate', result_schema_version: 2,
        findings: [], repair_groups: [{ group_id: 'scope-0', finding_ids: [0, 1], scope_summary: 'Shared exterior repair', observed_support: 'One connected damaged area.', possible_repair_approach: 'Provisional repair after inspection.', approach_is_hypothesis: true, parts: { status: 'provided', amount: { low: 2000, high: 3000 }, basis: 'Indicative parts allocation.' }, labor: { status: 'provided', amount: { low: 4000, high: 5000 }, basis: 'Indicative labor allocation.' }, paint_materials: { status: 'provided', amount: { low: 1000, high: 2000 }, basis: 'Indicative materials allocation.' }, other_charges: { status: 'not_applicable', amount: null, basis: 'No other charges included.' }, tax: { status: 'unknown', amount: null, basis: 'Excluded.' }, estimate_range: { low: 7000, high: 10000 }, unavailable_reason: null, assumptions: ['Pre-tax scenario.'], missing_information: [], pricing_basis: 'AI-generated indicative estimate.', professional_inspection_required: true, pricing_status: 'ai_estimate' }],
        cost_breakdown: { parts: { status: 'provided', amount: { low: 2000, high: 3000 }, basis: 'Combined scope.' } },
        total_status: 'available', vehicle_total: { low: 7000, high: 10000 }, partial_subtotal: null, total_reason: 'One consolidated scope.',
      },
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(grouped), { status: 200 })));
    const result = await calculateRepairCost('assessment-grouped');
    expect(result.ai_cost_estimate?.repair_groups?.[0].finding_ids).toEqual([0, 1]);
    expect(result.ai_cost_estimate?.cost_breakdown?.parts?.amount?.high).toBe(3000);
    expect(result.ai_cost_estimate?.vehicle_total?.high).toBe(10000);
  });

  it('preserves unavailable null pricing and surfaces request failures without example values', async () => {
    const unavailable = { ...responseFixture, ai_cost_estimate: { status: 'unavailable', pricing_status: 'estimate_unavailable', findings: [], total_status: 'estimate_unavailable', vehicle_total: null, partial_subtotal: null, total_reason: 'Gemini timed out.' } };
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(unavailable), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Service unavailable.' }), { status: 503 })));
    const result = await calculateRepairCost('assessment-a');
    expect(result.ai_cost_estimate?.vehicle_total).toBeNull();
    expect(result.ai_cost_estimate?.pricing_status).toBe('estimate_unavailable');
    await expect(calculateRepairCost('assessment-a')).rejects.toMatchObject({ status: 503 });
  });

  it('calls live Gemini diagnostics only on its explicit action', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'unavailable', category: 'timeout', message: 'Timed out.' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(runGeminiDiagnostic()).resolves.toMatchObject({ status: 'unavailable', category: 'timeout' });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/gemini/diagnostic', { method: 'POST' });
  });
});
