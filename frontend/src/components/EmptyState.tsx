import { ArrowRight, Inbox, ImagePlus, SearchX } from 'lucide-react';

interface EmptyStateProps {
  kind?: 'history' | 'dashboard' | 'findings' | 'search';
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({ kind = 'history', title, description, actionLabel, onAction }: EmptyStateProps) {
  const Icon = kind === 'dashboard' ? ImagePlus : kind === 'findings' ? SearchX : kind === 'search' ? SearchX : Inbox;
  return (
    <div className="flex min-h-[280px] flex-col items-center justify-center px-6 py-12 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-[16px] border border-line bg-canvas text-accent">
        <Icon size={24} strokeWidth={1.7} aria-hidden="true" />
      </span>
      <h2 className="mt-5 font-display text-xl font-semibold tracking-[-0.025em] text-ink">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted">{description}</p>
      {actionLabel && onAction && (
        <button type="button" className="button-secondary mt-6" onClick={onAction}>
          {actionLabel}
          <ArrowRight size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
