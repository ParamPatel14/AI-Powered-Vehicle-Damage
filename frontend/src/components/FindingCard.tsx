import { useEffect, useState } from 'react';
import { ChevronDown, CircleAlert, Crosshair, Ruler, Scan } from 'lucide-react';
import type { SeverityFinding } from '../types/assessment';
import { formatClassName, formatConfidence } from '../lib/formatters';
import { ReviewBadge, SeverityBadge } from './StatusBadge';
import { ReviewAlert } from './ReviewAlert';

interface FindingCardProps {
  finding: SeverityFinding;
  index: number;
  selected: boolean;
  onSelect: () => void;
}

export function FindingCard({ finding, index, selected, onSelect }: FindingCardProps) {
  const [detailsOpen, setDetailsOpen] = useState(selected);
  const evidence = finding.original_evidence;
  const maskPercent = finding.image_level_mask_area_percent;
  const polygonCount = evidence.polygons_xy?.length ?? 0;

  useEffect(() => {
    if (selected) setDetailsOpen(true);
  }, [selected]);

  return (
    <article className={`overflow-hidden rounded-[14px] border bg-panel transition duration-200 ${selected ? 'border-accent shadow-lift' : 'border-line shadow-panel hover:border-slate-300'}`}>
      <button type="button" className="block w-full text-left" onClick={onSelect} aria-pressed={selected}>
        <div className="flex items-start gap-4 px-4 py-4 sm:px-5">
          <span className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] text-sm font-bold ${selected ? 'bg-ink text-white' : 'bg-canvas text-muted'}`}>{String(index + 1).padStart(2, '0')}</span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-display text-lg font-semibold tracking-[-0.025em] text-ink">{formatClassName(evidence.class_name)}</h3>
              <SeverityBadge severity={finding.preliminary_severity} />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
              <span className="inline-flex items-center gap-1.5"><Crosshair size={13} aria-hidden="true" /> Detection {evidence.detection_id}</span>
              <span className="inline-flex items-center gap-1.5"><CircleAlert size={13} aria-hidden="true" /> Confidence {formatConfidence(evidence.confidence)}</span>
              {evidence.masks_available ? <span className="inline-flex items-center gap-1.5"><Scan size={13} aria-hidden="true" /> Segmentation available</span> : <span className="inline-flex items-center gap-1.5"><Scan size={13} aria-hidden="true" /> No mask returned</span>}
            </div>
          </div>
          <div className="hidden shrink-0 sm:block">
            <ReviewBadge required={finding.human_review_required} />
          </div>
        </div>
      </button>

      <div className="flex flex-wrap items-center gap-2 border-t border-line bg-canvas/35 px-4 py-2.5 sm:px-5">
        <div className="flex flex-1 flex-wrap items-center gap-2">
          <ReviewBadge required={finding.human_review_required} />
        </div>
        <button type="button" className="button-quiet min-h-8 px-2 text-xs" onClick={() => setDetailsOpen((value) => !value)} aria-expanded={detailsOpen}>
          {detailsOpen ? 'Hide details' : 'Details'}
          <ChevronDown size={14} className={`transition-transform ${detailsOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
        </button>
      </div>

      {detailsOpen && (
        <div className="space-y-4 border-t border-line px-4 py-4 sm:px-5 motion-enter">
          <div className="grid gap-3 sm:grid-cols-3">
            <Metric label="Preliminary severity" value={finding.preliminary_severity} />
            <Metric label="Visible mask footprint" value={typeof maskPercent === 'number' ? `${maskPercent.toFixed(2)}% of image` : 'Unavailable'} />
            <Metric label="Segmentation geometry" value={evidence.masks_available ? `${polygonCount} polygon${polygonCount === 1 ? '' : 's'}` : 'Not available'} />
          </div>

          <div className="rounded-[10px] border border-line bg-canvas/45 p-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.11em] text-muted"><Ruler size={14} aria-hidden="true" /> Why this label was assigned</div>
            <ul className="mt-2 space-y-1 text-xs leading-5 text-muted">
              {finding.severity_reasons.length ? finding.severity_reasons.map((reason, reasonIndex) => <li key={`${reason}-${reasonIndex}`}>• {reason}</li>) : <li>• No explanation was supplied by the assessment service.</li>}
            </ul>
          </div>

          {finding.inspection_flags.length > 0 && (
            <ReviewAlert title="Inspection flags" reasons={finding.inspection_flags.map((flag) => flag.reason)} compact />
          )}
          {finding.human_review_required && finding.inspection_flags.length === 0 && <ReviewAlert reasons={finding.human_review_reasons} compact />}
        </div>
      )}
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[10px] border border-line bg-canvas/45 px-3 py-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">{label}</p>
      <p className="mt-1 text-sm font-semibold text-ink">{value}</p>
    </div>
  );
}
