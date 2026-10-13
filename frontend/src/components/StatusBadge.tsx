import { AlertCircle, Check, Clock3, Eye, Minus, ShieldAlert } from 'lucide-react';
import { formatSeverity } from '../lib/formatters';

type StatusTone = 'success' | 'review' | 'warning' | 'neutral' | 'danger' | 'available';

interface StatusBadgeProps {
  label: string;
  tone?: StatusTone;
  icon?: boolean;
  className?: string;
}

const toneClasses: Record<StatusTone, string> = {
  success: 'border-sage/20 bg-sage-soft text-sage',
  review: 'border-amber/20 bg-amber-soft text-amber',
  warning: 'border-amber/20 bg-amber-soft text-amber',
  neutral: 'border-line bg-slate-50 text-muted',
  danger: 'border-coral/20 bg-coral-soft text-coral',
  available: 'border-accent/20 bg-accent-soft text-accent-dark',
};

function BadgeIcon({ tone }: { tone: StatusTone }) {
  if (tone === 'success') return <Check size={12} strokeWidth={2.5} aria-hidden="true" />;
  if (tone === 'review' || tone === 'warning') return <Eye size={12} strokeWidth={2.4} aria-hidden="true" />;
  if (tone === 'danger') return <ShieldAlert size={12} strokeWidth={2.3} aria-hidden="true" />;
  if (tone === 'available') return <Clock3 size={12} strokeWidth={2.3} aria-hidden="true" />;
  return <Minus size={12} strokeWidth={2.3} aria-hidden="true" />;
}

export function StatusBadge({ label, tone = 'neutral', icon = true, className = '' }: StatusBadgeProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${toneClasses[tone]} ${className}`}>
      {icon && <BadgeIcon tone={tone} />}
      {label}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  const tone: StatusTone = severity === 'major' ? 'danger' : severity === 'moderate' ? 'review' : severity === 'minor' ? 'available' : 'neutral';
  return <StatusBadge label={formatSeverity(severity)} tone={tone} />;
}

export function ReviewBadge({ required }: { required: boolean }) {
  return required ? <StatusBadge label="Requires review" tone="review" /> : <StatusBadge label="Reviewed" tone="success" />;
}

export function EstimateBadge({ status, requiresReview }: { status: string; requiresReview: boolean }) {
  if (status === 'conditional_estimate_available') {
    return <StatusBadge label={requiresReview ? 'Scenario · review' : 'Estimated scenario'} tone={requiresReview ? 'review' : 'success'} />;
  }
  if (status === 'not_estimated') return <StatusBadge label="Not estimated" tone="neutral" />;
  return <StatusBadge label="Unavailable" tone="danger" />;
}

export function ServiceBadge({ ready }: { ready: boolean | null }) {
  if (ready === true) return <StatusBadge label="Connected" tone="success" />;
  if (ready === false) return <StatusBadge label="Unavailable" tone="danger" />;
  return <StatusBadge label="Checking" tone="neutral" />;
}

export function ErrorBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-coral">
      <AlertCircle size={14} aria-hidden="true" />
      {label}
    </span>
  );
}
