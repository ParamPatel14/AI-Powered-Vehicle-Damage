import { LoaderCircle } from 'lucide-react';

interface LoadingStateProps {
  label: string;
  compact?: boolean;
}

export function LoadingState({ label, compact = false }: LoadingStateProps) {
  return (
    <div className={`flex items-center gap-3 text-sm text-muted ${compact ? 'py-3' : 'min-h-[220px] justify-center'}`} role="status" aria-live="polite">
      <LoaderCircle className="animate-spin text-accent" size={18} aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
