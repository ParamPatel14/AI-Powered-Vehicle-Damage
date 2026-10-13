import { ShieldAlert } from 'lucide-react';

interface ReviewAlertProps {
  title?: string;
  reasons: string[];
  compact?: boolean;
}

export function ReviewAlert({ title = 'Human review is required', reasons, compact = false }: ReviewAlertProps) {
  const visibleReasons = reasons.filter(Boolean).slice(0, compact ? 2 : 6);
  return (
    <div className={`border border-amber/20 bg-amber-soft/65 ${compact ? 'rounded-[10px] p-3' : 'rounded-[12px] p-4'}`}>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber/10 text-amber">
          <ShieldAlert size={15} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-amber">{title}</p>
          {visibleReasons.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs leading-5 text-[#85531d]">
              {visibleReasons.map((reason, index) => <li key={`${reason}-${index}`}>• {reason}</li>)}
            </ul>
          )}
          {reasons.length > visibleReasons.length && <p className="mt-2 text-[11px] font-semibold text-amber">+ {reasons.length - visibleReasons.length} more review considerations</p>}
        </div>
      </div>
    </div>
  );
}
