import { useState } from 'react';
import { BookOpen, ChevronDown, ShieldCheck, Sparkles } from 'lucide-react';
import type { AssessmentResponse, AiSummaryResult } from '../types/assessment';
import { StatusBadge } from './StatusBadge';

export function GeminiReportSections({ response, selectedId }: { response: AssessmentResponse; selectedId: number | null }) {
  const result = response.ai_summary;
  if (!result) return <section className="mt-10 rounded-[12px] border border-line bg-panel p-5"><p className="eyebrow">AI summary</p><p className="mt-2 text-sm text-muted">Not requested. Use Generate AI Summary to interpret these findings.</p></section>;
  const summary = result.summary;
  const explanation = summary?.findings_explanations.find((item) => item.finding_id === selectedId);
  return <section className="mt-10" aria-labelledby="ai-assessment-heading">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow">AI interpretation</p><h2 id="ai-assessment-heading" className="mt-2 font-display text-2xl font-semibold tracking-[-0.035em]">A clearer read, with its limits.</h2></div><StatusBadge label={result.status === 'completed' ? 'AI summary generated' : result.status.replaceAll('_', ' ')} tone={result.status === 'completed' ? 'available' : 'review'} /></div>
    {summary ? <>
      <div className="mt-4 rounded-[14px] border border-accent/15 bg-accent-soft/35 p-5 sm:p-6"><div className="flex items-center gap-2 text-sm font-semibold text-ink"><Sparkles size={16} className="text-accent" />Executive summary</div><p className="mt-3 text-sm leading-6 text-ink">{summary.summary}</p></div>
      {explanation && <div className="mt-4 rounded-[12px] border border-line bg-panel p-4"><p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted">Finding {explanation.finding_id} · explanation</p><p className="mt-2 text-sm leading-6 text-ink">{explanation.plain_language}</p><div className="mt-3 grid gap-3 sm:grid-cols-2">{[['Technical context', explanation.technical_context], ['Confidence', explanation.confidence_context], ['Severity', explanation.severity_context], ['Review flags', explanation.review_reasons.join(' ') || 'No additional AI review reason.']].map(([label, value]) => <div key={label}><p className="text-xs font-semibold text-muted">{label}</p><p className="mt-1 text-xs leading-5 text-ink">{value}</p></div>)}</div></div>}
      <div className="mt-4 grid gap-4 md:grid-cols-2"><List title="Recommended inspection steps" items={summary.recommended_next_steps} /><List title="What this system cannot conclude" items={summary.limitations} /></div>
      <SummaryDetails summary={summary} />
      <Insurance summary={summary} />
    </> : <div className="mt-4 rounded-[12px] border border-coral/20 bg-coral-soft/40 p-4" role="alert"><p className="text-sm font-semibold text-ink">AI summary could not be generated</p><p className="mt-1 text-sm text-muted">{result.message}</p><p className="mt-2 text-xs text-muted">Detection evidence remains available and unchanged. Use the summary action above to retry.</p></div>}
  </section>;
}

function List({ title, items }: { title: string; items: string[] }) {
  return <section className="panel rounded-[12px] p-4"><h3 className="text-sm font-semibold text-ink">{title}</h3><ul className="mt-3 space-y-2 text-xs leading-5 text-muted">{items.map((item, index) => <li key={`${index}-${item}`}>• {item}</li>)}</ul></section>;
}

function SummaryDetails({ summary }: { summary: NonNullable<AiSummaryResult['summary']> }) {
  const [open, setOpen] = useState(false);
  return <section className="panel mt-4 overflow-hidden rounded-[12px]"><button type="button" className="flex w-full items-center justify-between px-4 py-3 text-left" onClick={() => setOpen((value) => !value)} aria-expanded={open}><span className="flex items-center gap-2 text-sm font-semibold text-ink"><BookOpen size={15} className="text-accent" />Technical glossary</span><ChevronDown size={15} className={`transition-transform ${open ? 'rotate-180' : ''}`} /></button>{open && <ul className="space-y-2 border-t border-line p-4 text-xs leading-5 text-muted">{summary.technical_glossary.map((item) => <li key={item.term}><strong className="text-ink">{item.term}:</strong> {item.explanation}</li>)}</ul>}</section>;
}

function Insurance({ summary }: { summary: NonNullable<AiSummaryResult['summary']> }) {
  const guidance = summary.insurance_guidance;
  return <section className="panel mt-4 overflow-hidden rounded-[12px]"><div className="flex items-center gap-2 border-b border-line px-4 py-3 text-sm font-semibold text-ink"><ShieldCheck size={15} className="text-accent" />Insurance guidance</div><div className="p-4"><StatusBadge label={guidance.policy_category.replaceAll('_', ' ')} tone="neutral" /><p className="mt-3 text-sm leading-6 text-ink">{guidance.summary}</p><p className="mt-2 text-xs leading-5 text-muted">{guidance.general_coverage_context}</p><div className="mt-3 space-y-2">{guidance.finding_guidance.map((finding) => <details key={finding.finding_id} className="rounded-[9px] border border-line p-3"><summary className="cursor-pointer text-xs font-semibold text-ink">Finding {finding.finding_id}: {finding.potential_coverage_category}</summary><p className="mt-2 text-[11px] leading-5 text-muted">Status: {finding.status.replaceAll('_', ' ')}</p><ul className="mt-1 space-y-1 text-[11px] leading-5 text-muted">{[...finding.conditions, ...finding.missing_information].map((item) => <li key={item}>• {item}</li>)}</ul></details>)}</div><ul className="mt-3 space-y-1 text-xs leading-5 text-muted">{guidance.policy_questions.map((item) => <li key={item}>• {item}</li>)}</ul><p className="mt-3 text-[11px] leading-5 text-muted">{guidance.disclaimer} This is guidance only, not claim approval.</p></div></section>;
}
