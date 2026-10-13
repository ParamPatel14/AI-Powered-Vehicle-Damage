import { useEffect, useState } from 'react';
import { ArrowLeft, CalendarClock, ClipboardCheck, Download, FileText, Flag, Info, ShieldAlert, Sparkles } from 'lucide-react';
import type { AssessmentRecord } from '../types/assessment';
import { compactId, formatDate, formatRange } from '../lib/formatters';
import { PageHeader } from '../components/PageHeader';
import { EvidenceViewer } from '../components/EvidenceViewer';
import { FindingCard } from '../components/FindingCard';
import { EmptyState } from '../components/EmptyState';
import { ReviewAlert } from '../components/ReviewAlert';
import { StatusBadge } from '../components/StatusBadge';
import type { AiCostComponent, AiCostResult } from '../types/assessment';
import { GeminiReportSections } from '../components/GeminiReportSections';
import { apiUrl } from '../services/api';
import { calculateRepairCost, generateAiAssessment } from '../services/api';

interface AssessmentReportPageProps {
  record: AssessmentRecord;
  onUpdate: (response: AssessmentRecord['response']) => void;
  onBack: () => void;
  onNewAssessment: () => void;
}

export function AssessmentReportPage({ record, onUpdate, onBack, onNewAssessment }: AssessmentReportPageProps) {
  const { response } = record;
  const findings = response.severity_assessment.detections;
  const [selectedId, setSelectedId] = useState<number | null>(findings[0]?.original_evidence.detection_id ?? null);
  const [runningAction, setRunningAction] = useState<'summary' | 'cost' | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [failedAction, setFailedAction] = useState<'summary' | 'cost'>('cost');

  useEffect(() => {
    if (findings.length > 0 && !findings.some((finding) => finding.original_evidence.detection_id === selectedId)) {
      setSelectedId(findings[0].original_evidence.detection_id);
    }
  }, [findings, selectedId]);

  const aiCost = response.ai_cost_estimate;
  const legacyCost = aiCost?.status === 'completed' && aiCost.result_schema_version !== 2;
  const pdfUrl = record.pdfUrl || (response.artifacts?.pdf_url ? apiUrl(response.artifacts.pdf_url) : undefined);
  const needsReview = response.status === 'completed_with_human_review' || response.severity_assessment.summary.human_review_count > 0;

  const runGemini = async (action: 'summary' | 'cost') => {
    if (runningAction) return;
    setRunningAction(action);
    setActionError(null);
    setFailedAction(action);
    try {
      const updated = action === 'summary' ? await generateAiAssessment(response.assessment_id) : await calculateRepairCost(response.assessment_id);
      onUpdate(updated);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Gemini could not complete this request. Your detector findings are unchanged.');
    } finally {
      setRunningAction(null);
    }
  };

  return (
    <div className="motion-enter">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <button type="button" className="button-quiet -ml-2" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" /> Back to dashboard</button>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="button-secondary" disabled={runningAction !== null} onClick={() => void runGemini('summary')}><Sparkles size={15} aria-hidden="true" />{runningAction === 'summary' ? 'Generating…' : 'Generate AI Summary'}</button>
          <button type="button" className="button-primary" disabled={runningAction !== null} onClick={() => void runGemini('cost')}>{runningAction === 'cost' ? 'Calculating…' : 'Calculate Repair Cost'}</button>
          {pdfUrl && <a className="button-secondary" href={pdfUrl} download={`veyra-assessment-${response.assessment_id}.pdf`}><Download size={16} aria-hidden="true" /> Download PDF</a>}
          <button type="button" className="button-primary" onClick={onNewAssessment}><ClipboardCheck size={16} aria-hidden="true" /> New assessment</button>
        </div>
      </div>
      <PageHeader
        eyebrow="Assessment report"
        title="Evidence, organized."
        description={`${record.fileName} · Assessment ${compactId(response.assessment_id)}`}
        meta={<StatusBadge label={needsReview ? 'Preliminary · review required' : 'Preliminary'} tone={needsReview ? 'review' : 'success'} />}
      />

      <section className="mt-7 grid gap-3 sm:grid-cols-3" aria-label="Report summary">
        <SummaryCell icon={<Flag size={16} />} label="Findings returned" value={String(response.detection_report.detection_count)} detail={response.detection_report.detection_count === 1 ? 'One visual finding' : 'Visual findings from the image'} />
        <SummaryCell icon={<ShieldAlert size={16} />} label="Review queue" value={String(response.severity_assessment.summary.human_review_count)} detail={response.severity_assessment.summary.human_review_count > 0 ? 'Finding-level review flags' : 'No finding-level flags'} tone={response.severity_assessment.summary.human_review_count > 0 ? 'amber' : 'sage'} />
        <SummaryCell icon={<FileText size={16} />} label="Repair estimate" value={legacyCost ? 'Refresh estimate' : aiCost?.vehicle_total ? formatRange(aiCost.vehicle_total.low, aiCost.vehicle_total.high, 'INR') : aiCost?.partial_subtotal ? formatRange(aiCost.partial_subtotal.low, aiCost.partial_subtotal.high, 'INR') : aiCost?.repair_groups?.some((group) => group.estimate_range !== null) || aiCost?.findings.some((finding) => finding.estimate_range !== null) ? 'AI scopes estimated' : aiCost?.status === 'unavailable' ? 'Request failed' : aiCost?.status === 'completed' ? 'No range returned' : 'Not requested'} detail={legacyCost ? 'Generate a consolidated estimate for this assessment' : aiCost?.total_reason || 'Run an explicit Gemini cost request for this image'} />
      </section>

      <div className="mt-5 flex items-start gap-3 rounded-[12px] border border-amber/20 bg-amber-soft/65 p-4 text-xs leading-5 text-[#85531d]">
        <Info size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
        <p>{response.severity_assessment.disclaimer}</p>
      </div>

      <div className="mt-7 grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(330px,0.8fr)]">
        <EvidenceViewer response={response} imageUrl={record.previewUrl} sourceImageUrl={record.sourceImageUrl} annotatedImageUrl={record.annotatedPreviewUrl} fileName={record.fileName} selectedId={selectedId} onSelectFinding={setSelectedId} />
        <VehicleTotalCard result={aiCost} running={runningAction === 'cost'} error={runningAction === 'cost' ? null : actionError && failedAction === 'cost' ? actionError : null} onCalculate={() => void runGemini('cost')} onRetry={() => void runGemini('cost')} />
      </div>
      {actionError && failedAction === 'summary' && <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-coral/20 bg-coral-soft/50 p-3 text-sm text-[#86463d]" role="alert"><p>{actionError}</p><button type="button" className="font-semibold underline" disabled={runningAction !== null} onClick={() => void runGemini('summary')}>Retry AI summary</button></div>}

      <section className="mt-10" aria-labelledby="findings-heading">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div><p className="eyebrow">Detection detail</p><h2 id="findings-heading" className="mt-2 font-display text-2xl font-semibold tracking-[-0.035em]">Findings from the image</h2></div>
          <p className="text-xs text-muted">Select a finding to focus its geometry on the image.</p>
        </div>
        <div className="mt-4 space-y-4">
          {findings.length === 0 ? (
            <div className="panel rounded-[16px]"><EmptyState kind="findings" title="No findings were returned" description="This does not establish that the vehicle has no damage. It means the service returned no detectable findings for this image." /></div>
          ) : findings.map((finding, index) => (
            <FindingCard key={`${finding.original_evidence.detection_id}-${index}`} finding={finding} index={index} selected={selectedId === finding.original_evidence.detection_id} onSelect={() => setSelectedId(finding.original_evidence.detection_id)} />
          ))}
        </div>
      </section>

      <GeminiReportSections response={response} selectedId={selectedId} />

      <section className="mt-10 grid gap-5 md:grid-cols-2" aria-label="Report notes">
        {needsReview && <ReviewAlert title="Human review remains part of this report" reasons={findings.flatMap((finding) => finding.human_review_reasons).slice(0, 6)} />}
        <div className={`panel rounded-[14px] p-5 ${!needsReview ? 'md:col-span-2' : ''}`}>
          <div className="flex items-center gap-2"><CalendarClock size={16} className="text-accent" aria-hidden="true" /><p className="text-sm font-semibold text-ink">Report metadata</p></div>
          <div className="mt-4 grid gap-3 text-xs sm:grid-cols-2">
            <MetaRow label="Created" value={formatDate(record.createdAt)} />
            <MetaRow label="Source image" value={record.fileName} />
            <MetaRow label="Image dimensions" value={`${response.detection_report.image_width} × ${response.detection_report.image_height}px`} />
            <MetaRow label="Assessment ID" value={response.assessment_id} mono />
          </div>
        </div>
      </section>

      <p className="mt-8 text-center text-[11px] leading-5 text-muted">Veyra provides a preliminary, image-based assessment for review. It is not a professional inspection, roadworthiness decision, insurance approval, or guaranteed quotation.</p>
    </div>
  );
}

function SummaryCell({ icon, label, value, detail, tone = 'accent' }: { icon: React.ReactNode; label: string; value: string; detail: string; tone?: 'accent' | 'amber' | 'sage' }) {
  const iconTone = tone === 'amber' ? 'bg-amber-soft text-amber' : tone === 'sage' ? 'bg-sage-soft text-sage' : 'bg-accent-soft text-accent';
  return <div className="panel rounded-[13px] p-4"><div className="flex items-center gap-3"><span className={`flex h-8 w-8 items-center justify-center rounded-[9px] ${iconTone}`}>{icon}</span><p className="eyebrow">{label}</p></div><p className="mt-4 font-display text-2xl font-semibold tracking-[-0.04em] text-ink">{value}</p><p className="mt-1 text-xs text-muted">{detail}</p></div>;
}

function VehicleTotalCard({ result, running, error, onCalculate, onRetry }: { result?: AiCostResult; running: boolean; error: string | null; onCalculate: () => void; onRetry: () => void }) {
  const amount = result?.vehicle_total || result?.partial_subtotal;
  const scopes = result?.repair_groups ?? [];
  const pricedScopes = scopes.filter((scope) => scope.estimate_range !== null);
  const componentValue = (component?: AiCostComponent) => !component || component.status === 'unknown' ? 'Not itemized' : component.status === 'not_applicable' ? 'Not included' : component.amount ? formatRange(component.amount.low, component.amount.high, 'INR') : 'Not itemized';
  const componentRows = [
    ['Parts', result?.cost_breakdown?.parts],
    ['Labor', result?.cost_breakdown?.labor],
    ['Paint / materials', result?.cost_breakdown?.paint_materials],
    ['Other charges', result?.cost_breakdown?.other_charges],
    ['Taxes', result?.cost_breakdown?.tax],
  ] as const;
  const legacyResult = result?.status === 'completed' && result.result_schema_version !== 2;

  return (
    <section className="panel overflow-hidden rounded-[16px]" aria-labelledby="vehicle-total-heading">
      <div className="border-b border-line px-5 py-4 sm:px-6"><p className="eyebrow">Repair assessment</p><h2 id="vehicle-total-heading" className="mt-1 font-display text-xl font-semibold tracking-[-0.025em]">AI repair estimate</h2></div>
      <div className="p-5 sm:p-6">
        {running ? <div className="rounded-[10px] bg-canvas/60 p-4" role="status"><span className="loading-spinner" /> <span className="ml-2 text-sm text-muted">Preparing one consolidated image-specific estimate...</span></div> : <>
          {error && <div className="mb-4 rounded-[10px] border border-coral/20 bg-coral-soft/45 p-3 text-sm text-[#86463d]" role="alert"><p className="font-semibold">The latest cost request failed.</p><p className="mt-1 text-xs leading-5">{error}{result?.status === 'completed' ? ' The last completed result remains below.' : ''}</p><button type="button" className="mt-2 font-semibold underline" onClick={onRetry}>Retry assessment</button></div>}
          {!result ? <><StatusBadge label="Not requested" tone="neutral" /><p className="mt-3 text-sm leading-6 text-muted">Generate one AI repair assessment with an overall range and itemized breakdown.</p><button type="button" className="button-primary mt-4 w-full justify-center" onClick={onCalculate}>Calculate Repair Cost</button></> : legacyResult ? <div className="rounded-[10px] bg-canvas/60 p-4"><p className="text-sm font-semibold text-ink">A previous per-finding estimate is saved.</p><p className="mt-1 text-xs leading-5 text-muted">Generate a consolidated assessment to group overlapping findings and show one overall range with a single breakdown.</p><button type="button" className="button-primary mt-3 w-full justify-center" onClick={onRetry}>Generate consolidated estimate</button></div> : result.status !== 'completed' ? <div className="rounded-[10px] border border-coral/20 bg-coral-soft/45 p-3 text-sm text-[#86463d]" role="alert"><p>{error ? '' : result.message}</p>{!error && <button type="button" className="mt-3 font-semibold underline" onClick={onRetry}>Retry assessment</button>}</div> : <>
            <div className="flex flex-wrap items-center justify-between gap-3"><StatusBadge label={result.pricing_status === 'ai_estimate' ? 'AI estimate' : 'No estimate returned'} tone={result.pricing_status === 'ai_estimate' ? 'available' : 'review'} /><p className="text-xs font-semibold text-muted">INR · indicative, not a verified workshop price</p></div>
            {amount ? <><p className="mt-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">{result.vehicle_total ? 'Estimated repair total' : 'Partial estimate'}</p><p className="mt-1 font-display text-[clamp(1.8rem,4vw,2.65rem)] font-semibold leading-none tracking-[-0.05em] text-ink">{formatRange(amount.low, amount.high, 'INR')}</p></> : <p className="mt-4 font-display text-lg font-semibold text-ink">{pricedScopes.length ? 'Scope estimates are available; overall total withheld' : 'Gemini could not estimate this repair scope'}</p>}
            {result.total_reason && <p className="mt-2 text-xs leading-5 text-muted">{result.total_reason}</p>}
            {result.pricing_status === 'ai_estimate' && <section className="mt-5 border-t border-line pt-4"><h3 className="text-xs font-semibold text-ink">One combined cost breakdown</h3><dl className="mt-2 divide-y divide-line rounded-[9px] bg-canvas/50 px-3">{componentRows.map(([label, component]) => <div key={label} className="flex items-center justify-between gap-4 py-2"><dt className="text-xs text-muted">{label}</dt><dd className="text-right text-xs font-semibold text-ink">{label === 'Taxes' ? 'Excluded; not verified' : componentValue(component)}</dd></div>)}</dl></section>}
            {scopes.length === 1 && <details className="mt-4 border-t border-line pt-3"><summary className="cursor-pointer text-xs font-semibold text-accent-dark">Repair scope and assumptions</summary><p className="mt-2 text-xs font-semibold text-ink">{scopes[0].scope_summary} · Findings {scopes[0].finding_ids.map((id) => `#${id}`).join(', ')}</p><p className="mt-1 text-xs leading-5 text-muted">{scopes[0].observed_support} {scopes[0].possible_repair_approach}</p><p className="mt-1 text-xs leading-5 text-muted">Basis: {scopes[0].pricing_basis} {scopes[0].assumptions.join(' ')}{scopes[0].missing_information.length ? ` Missing: ${scopes[0].missing_information.join(' ')}` : ''}{scopes[0].unavailable_reason ? ` Estimate unavailable: ${scopes[0].unavailable_reason}` : ''}</p></details>}
            {scopes.length > 1 && <details className="mt-4 border-t border-line pt-3"><summary className="cursor-pointer text-xs font-semibold text-accent-dark">{scopes.length} distinct repair scopes</summary><div className="mt-2 divide-y divide-line">{scopes.map((scope) => <div key={scope.group_id} className="py-2"><div className="flex justify-between gap-3"><p className="text-xs font-semibold text-ink">{scope.scope_summary} · Findings {scope.finding_ids.map((id) => `#${id}`).join(', ')}</p><p className="shrink-0 text-xs font-semibold text-ink">{scope.estimate_range ? formatRange(scope.estimate_range.low, scope.estimate_range.high, 'INR') : 'No range'}</p></div><p className="mt-1 text-[11px] leading-4 text-muted">{scope.possible_repair_approach} {scope.assumptions.join(' ')}{scope.unavailable_reason ? ` ${scope.unavailable_reason}` : ''}</p></div>)}</div></details>}
            {pricedScopes.length === 0 && <div className="mt-3 rounded-[9px] bg-canvas/65 p-3"><p className="text-xs leading-5 text-muted">No range was returned. The saved detection findings are unchanged.</p><button type="button" className="mt-2 text-xs font-semibold text-accent-dark underline" onClick={onRetry}>Retry AI repair estimate</button></div>}
            {result.assumptions.length > 0 && <details className="mt-4 border-t border-line pt-3"><summary className="cursor-pointer text-xs font-semibold text-ink">Assessment assumptions</summary><ul className="mt-2 space-y-1 text-xs leading-5 text-muted">{result.assumptions.map((item) => <li key={item}>• {item}</li>)}</ul></details>}
            <p className="mt-4 text-[11px] leading-5 text-muted">AI-generated indicative assessment, not a workshop quote. Have a qualified workshop inspect the vehicle before repair decisions.</p>
          </>}
        </>}
      </div>
    </section>
  );
}

function MetaRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="min-w-0"><p className="font-semibold uppercase tracking-[0.1em] text-muted">{label}</p><p className={`mt-1 truncate text-ink ${mono ? 'font-mono text-[11px]' : 'font-medium'}`}>{value}</p></div>;
}
