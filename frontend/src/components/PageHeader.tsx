import { ArrowUpRight } from 'lucide-react';

interface PageHeaderProps {
  eyebrow: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
  meta?: React.ReactNode;
}

export function PageHeader({ eyebrow, title, description, action, meta }: PageHeaderProps) {
  return (
    <header className="flex flex-col gap-5 border-b border-line pb-7 sm:flex-row sm:items-end sm:justify-between sm:gap-8">
      <div className="min-w-0">
        <p className="eyebrow">{eyebrow}</p>
        <div className="mt-3 flex items-center gap-2">
          <h1 className="font-display text-[clamp(2rem,4vw,3.2rem)] font-semibold leading-[1.03] tracking-[-0.045em] text-ink">{title}</h1>
          {meta ?? <ArrowUpRight className="mt-1 hidden text-accent sm:block" size={22} aria-hidden="true" />}
        </div>
        {description && <p className="mt-3 max-w-2xl text-[15px] leading-7 text-muted">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}
