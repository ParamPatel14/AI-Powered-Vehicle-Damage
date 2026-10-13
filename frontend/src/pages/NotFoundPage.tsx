import { EmptyState } from '../components/EmptyState';

interface NotFoundPageProps {
  onDashboard: () => void;
}

export function NotFoundPage({ onDashboard }: NotFoundPageProps) {
  return <div className="panel rounded-[16px] motion-enter"><EmptyState kind="search" title="That report is not available" description="The requested view is not present in the current session. Start from the dashboard to see available assessment records." actionLabel="Back to dashboard" onAction={onDashboard} /></div>;
}
