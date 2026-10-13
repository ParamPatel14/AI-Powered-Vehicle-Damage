import { ArrowRight, FilePlus2, FolderOpen, Gauge, RefreshCw, ShieldCheck } from 'lucide-react';
import type { AssessmentRecord } from '../types/assessment';
import { formatClassName, formatDate } from '../lib/formatters';
import { PageHeader } from '../components/PageHeader';
import { EmptyState } from '../components/EmptyState';
import { ReviewBadge, ServiceBadge, SeverityBadge, StatusBadge } from '../components/StatusBadge';

interface DashboardPageProps {
  records: AssessmentRecord[];
  serviceReady: boolean | null;
  onNewAssessment: () => void;
  onOpenAssessment: (id: string) => void;
}

export function DashboardPage({ records, serviceReady, onNewAssessment, onOpenAssessment }: DashboardPageProps) {
  const reviewCount = records.filter((record) => record.response.severity_assessment.summary.human_review_count > 0).length;
  const findingCount = records.reduce((count, record) => count + record.response.detection_report.detection_count, 0);

  return (
    <div className="motion-enter">
      <PageHeader
        eyebrow="Inspection workspace"
        title="Read the vehicle clearly."
        description="A focused workspace for turning vehicle images into structured, provisional assessment reports."
        action={<button type="button" className="button-primary" onClick={onNewAssessment}><FilePlus2 size={17} aria-hidden="true" /> New assessment</button>}
      />

      <section className="mt-8 grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
        <div className="relative overflow-hidden rounded-[16px] bg-ink px-6 py-7 text-white shadow-lift sm:px-8 sm:py-9">
          <div className="absolute -right-16 -top-20 h-56 w-56 rounded-full border border-white/10" />
          <div className="absolute -right-6 -top-10 h-36 w-36 rounded-full border border-white/10" />
          <p className="eyebrow text-white/55">The next inspection</p>
          <h2 className="mt-4 max-w-xl font-display text-[clamp(1.8rem,3vw,2.65rem)] font-semibold leading-[1.08] tracking-[-0.045em]">Start with one clear image.</h2>
          <p className="mt-4 max-w-lg text-sm leading-6 text-white/65">Upload a JPEG or PNG to receive detector findings, provisional severity, and review flags. Request an AI summary or cost estimate separately after detection.</p>
          <button type="button" className="mt-7 inline-flex min-h-11 items-center gap-2 rounded-[10px] bg-white px-4 text-sm font-semibold text-ink transition hover:-translate-y-0.5 hover:bg-[#f3f7f8]" onClick={onNewAssessment}>
            Upload vehicle image
            <ArrowRight size={16} aria-hidden="true" />
          </button>
          <div className="mt-8 flex items-center gap-2 text-xs font-semibold text-white/65">
            <span className={`h-2 w-2 rounded-full ${serviceReady ? 'bg-[#9fd4bc]' : serviceReady === false ? 'bg-[#e39a8d]' : 'bg-white/40'}`} />
            {serviceReady ? 'Assessment API ready' : serviceReady === false ? 'Assessment API unavailable' : 'Checking assessment API'}
          </div>
        </div>

        <div className="panel rounded-[16px] p-5 sm:p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="eyebrow">Workspace readout</p>
              <h2 className="mt-2 font-display text-xl font-semibold tracking-[-0.025em]">This session</h2>
            </div>
            <ServiceBadge ready={serviceReady} />
          </div>
          <div className="mt-7 divide-y divide-line border-y border-line">
            <ReadoutRow icon={<FolderOpen size={16} />} label="Assessments" value={String(records.length)} />
            <ReadoutRow icon={<Gauge size={16} />} label="Findings returned" value={String(findingCount)} />
            <ReadoutRow icon={<ShieldCheck size={16} />} label="Reports needing review" value={String(reviewCount)} />
          </div>
          <p className="mt-5 text-xs leading-5 text-muted">Counts reflect only assessments created in this browser session. The backend does not currently expose durable history.</p>
        </div>
      </section>

      <section className="mt-10" aria-labelledby="recent-heading">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow">Session activity</p>
            <h2 id="recent-heading" className="mt-2 font-display text-2xl font-semibold tracking-[-0.035em]">Recent assessments</h2>
          </div>
          <button type="button" className="button-quiet" onClick={onNewAssessment}><RefreshCw size={15} aria-hidden="true" /> Start another</button>
        </div>
        <div className="panel mt-4 overflow-hidden rounded-[16px]">
          {records.length === 0 ? (
            <EmptyState
              kind="dashboard"
              title="Your assessment queue is clear"
              description="Your first report will appear here after you upload a vehicle image and complete an analysis."
              actionLabel="Create first assessment"
              onAction={onNewAssessment}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[700px] border-collapse text-left">
                <thead className="border-b border-line bg-canvas/55">
                  <tr className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted">
                    <th className="px-5 py-3.5 font-semibold">Source image</th>
                    <th className="px-4 py-3.5 font-semibold">Findings</th>
                    <th className="px-4 py-3.5 font-semibold">Report status</th>
                    <th className="px-4 py-3.5 font-semibold">Review</th>
                    <th className="px-5 py-3.5 text-right font-semibold">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {records.slice(0, 6).map((record) => {
                    const response = record.response;
                    const firstFinding = response.severity_assessment.detections[0];
                    const needsReview = response.severity_assessment.summary.human_review_count > 0;
                    return (
                      <tr key={response.assessment_id} className="group transition hover:bg-canvas/45">
                        <td className="px-5 py-4">
                          <button type="button" className="flex max-w-[300px] items-center gap-3 text-left" onClick={() => onOpenAssessment(response.assessment_id)}>
                            <img src={record.previewUrl} alt="" className="h-10 w-14 rounded-[6px] border border-line bg-ink object-cover" />
                            <span className="min-w-0">
                              <span className="block truncate text-sm font-semibold text-ink group-hover:text-accent">{record.fileName}</span>
                              <span className="mt-1 block text-xs text-muted">Assessment {response.assessment_id.slice(0, 8)}</span>
                            </span>
                          </button>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-ink">{response.detection_report.detection_count}</span>
                            {firstFinding && <SeverityBadge severity={firstFinding.preliminary_severity} />}
                          </div>
                          {firstFinding && <p className="mt-1 text-xs text-muted">{formatClassName(firstFinding.original_evidence.class_name)}{response.detection_report.detection_count > 1 ? ' and more' : ''}</p>}
                        </td>
                        <td className="px-4 py-4"><StatusBadge label={response.status === 'completed_with_human_review' ? 'Completed · review' : 'Completed'} tone={response.status === 'completed_with_human_review' ? 'review' : 'success'} /></td>
                        <td className="px-4 py-4"><ReviewBadge required={needsReview} /></td>
                        <td className="px-5 py-4 text-right text-xs text-muted">{formatDate(record.createdAt)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function ReadoutRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-4">
      <div className="flex items-center gap-3 text-sm text-muted"><span className="text-accent">{icon}</span>{label}</div>
      <span className="font-display text-xl font-semibold tracking-[-0.03em] text-ink">{value}</span>
    </div>
  );
}
