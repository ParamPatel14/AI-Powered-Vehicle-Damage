import { ExternalLink, History as HistoryIcon } from 'lucide-react';
import type { AssessmentRecord } from '../types/assessment';
import { formatDate, formatClassName } from '../lib/formatters';
import { PageHeader } from '../components/PageHeader';
import { EmptyState } from '../components/EmptyState';
import { ReviewBadge, StatusBadge } from '../components/StatusBadge';

interface HistoryPageProps {
  records: AssessmentRecord[];
  onNewAssessment: () => void;
  onOpenAssessment: (id: string) => void;
}

export function HistoryPage({ records, onNewAssessment, onOpenAssessment }: HistoryPageProps) {
  return (
    <div className="motion-enter">
      <PageHeader
        eyebrow="Assessment history"
        title="Your inspection trail."
        description="Review reports created during the current frontend session."
        action={<button type="button" className="button-primary" onClick={onNewAssessment}><HistoryIcon size={17} aria-hidden="true" /> New assessment</button>}
      />
      <div className="mt-7 flex items-start gap-3 rounded-[12px] border border-accent/15 bg-accent-soft/40 p-4 text-xs leading-5 text-accent-dark">
        <HistoryIcon size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
        <p><span className="font-semibold">Session-only history.</span> The current backend does not expose an assessment list or durable record store, so this table contains only reports created in this browser tab and clears when the page is refreshed.</p>
      </div>
      <section className="panel mt-6 overflow-hidden rounded-[16px]" aria-labelledby="history-table-heading">
        <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
          <div><p className="eyebrow">Current session</p><h2 id="history-table-heading" className="mt-1 font-display text-lg font-semibold tracking-[-0.02em]">Assessment records <span className="ml-1 text-muted">({records.length})</span></h2></div>
        </div>
        {records.length === 0 ? (
          <EmptyState kind="history" title="No reports yet" description="Complete an assessment and the result will remain available here for this session." actionLabel="Create an assessment" onAction={onNewAssessment} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-left">
              <thead className="border-b border-line bg-canvas/55"><tr className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted"><th className="px-5 py-3.5 font-semibold">Image</th><th className="px-4 py-3.5 font-semibold">Findings</th><th className="px-4 py-3.5 font-semibold">Assessment status</th><th className="px-4 py-3.5 font-semibold">Review state</th><th className="px-5 py-3.5 text-right font-semibold">Date</th><th className="px-5 py-3.5" /></tr></thead>
              <tbody className="divide-y divide-line">
                {records.map((record) => {
                  const response = record.response;
                  const first = response.severity_assessment.detections[0];
                  const review = response.severity_assessment.summary.human_review_count > 0;
                  return (
                    <tr key={response.assessment_id} className="group transition hover:bg-canvas/45">
                      <td className="px-5 py-4"><button type="button" className="flex max-w-[270px] items-center gap-3 text-left" onClick={() => onOpenAssessment(response.assessment_id)}><img src={record.previewUrl} alt="" className="h-10 w-14 rounded-[6px] border border-line bg-ink object-cover" /><span className="min-w-0"><span className="block truncate text-sm font-semibold text-ink group-hover:text-accent">{record.fileName}</span><span className="mt-1 block text-xs text-muted">{response.assessment_id.slice(0, 8)}</span></span></button></td>
                      <td className="px-4 py-4"><span className="text-sm font-semibold text-ink">{response.detection_report.detection_count}</span>{first && <p className="mt-1 text-xs text-muted">{formatClassName(first.original_evidence.class_name)}</p>}</td>
                      <td className="px-4 py-4"><StatusBadge label={response.status === 'completed_with_human_review' ? 'Completed · review' : 'Completed'} tone={response.status === 'completed_with_human_review' ? 'review' : 'success'} /></td>
                      <td className="px-4 py-4"><ReviewBadge required={review} /></td>
                      <td className="px-5 py-4 text-right text-xs text-muted">{formatDate(record.createdAt)}</td>
                      <td className="px-5 py-4 text-right"><button type="button" className="button-quiet px-2 text-xs" onClick={() => onOpenAssessment(response.assessment_id)}>Open <ExternalLink size={14} aria-hidden="true" /></button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
