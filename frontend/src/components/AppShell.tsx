import { useState } from 'react';
import {
  Activity,
  ClipboardCheck,
  FilePlus2,
  History,
  Menu,
  PanelLeftClose,
  Settings2,
  X,
} from 'lucide-react';
import { BrandMark } from './BrandMark';

export type AppRoute = 'dashboard' | 'new-assessment' | 'history' | 'settings' | 'report' | 'not-found';

interface AppShellProps {
  route: AppRoute;
  onNavigate: (route: Exclude<AppRoute, 'report' | 'not-found'>) => void;
  serviceReady: boolean | null;
  children: React.ReactNode;
}

const navigation = [
  { key: 'dashboard' as const, label: 'Dashboard', icon: ClipboardCheck },
  { key: 'new-assessment' as const, label: 'New assessment', icon: FilePlus2 },
  { key: 'history' as const, label: 'Assessment history', icon: History },
  { key: 'settings' as const, label: 'Settings', icon: Settings2 },
];

export function AppShell({ route, onNavigate, serviceReady, children }: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleNavigate = (nextRoute: Exclude<AppRoute, 'report' | 'not-found'>) => {
    setMobileOpen(false);
    onNavigate(nextRoute);
  };

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] flex-col border-r border-line bg-[#f8f7f3] px-5 py-6 lg:flex">
        <div className="px-2">
          <BrandMark />
        </div>
        <div className="mt-12 px-2">
          <p className="eyebrow">Workspace</p>
          <nav className="mt-4 space-y-1" aria-label="Primary navigation">
            {navigation.map((item) => {
              const Icon = item.icon;
              const active = route === item.key || (route === 'report' && item.key === 'history');
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => handleNavigate(item.key)}
                  className={`group flex w-full items-center gap-3 rounded-[10px] px-3 py-3 text-left text-sm font-semibold transition ${
                    active
                      ? 'bg-ink text-white shadow-sm'
                      : 'text-muted hover:bg-white hover:text-ink'
                  }`}
                  aria-current={active ? 'page' : undefined}
                >
                  <Icon size={18} strokeWidth={active ? 2.1 : 1.8} aria-hidden="true" />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        <div className="mt-auto space-y-4 px-2">
          <div className="rounded-[12px] border border-line bg-white/70 p-3">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${serviceReady ? 'bg-sage' : serviceReady === false ? 'bg-coral' : 'bg-slate-300'}`} />
              <span className="text-xs font-semibold text-ink">
                {serviceReady ? 'Service ready' : serviceReady === false ? 'Service unavailable' : 'Checking service'}
              </span>
            </div>
            <p className="mt-2 text-[11px] leading-5 text-muted">Image analysis and provisional reporting are available through the connected API.</p>
          </div>
          <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">Veyra / Stage 5</p>
        </div>
      </aside>

      <header className="sticky top-0 z-20 flex h-[68px] items-center justify-between border-b border-line bg-[#f8f7f3]/95 px-5 backdrop-blur lg:hidden">
        <BrandMark compact />
        <button
          type="button"
          className="button-quiet min-h-10 px-2"
          onClick={() => setMobileOpen((open) => !open)}
          aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'}
          aria-expanded={mobileOpen}
        >
          {mobileOpen ? <X size={21} /> : <Menu size={21} />}
        </button>
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-label="Mobile navigation">
          <button
            type="button"
            className="absolute inset-0 bg-ink/20"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation overlay"
          />
          <div className="relative ml-auto min-h-full w-[min(320px,88vw)] border-l border-line bg-[#f8f7f3] px-5 py-6 shadow-lift motion-enter">
            <div className="flex items-center justify-between">
              <BrandMark />
              <button type="button" className="button-quiet px-2" onClick={() => setMobileOpen(false)} aria-label="Close navigation">
                <PanelLeftClose size={19} />
              </button>
            </div>
            <nav className="mt-12 space-y-1" aria-label="Mobile primary navigation">
              {navigation.map((item) => {
                const Icon = item.icon;
                const active = route === item.key || (route === 'report' && item.key === 'history');
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => handleNavigate(item.key)}
                    className={`flex w-full items-center gap-3 rounded-[10px] px-3 py-3 text-left text-sm font-semibold transition ${
                      active ? 'bg-ink text-white' : 'text-muted hover:bg-white hover:text-ink'
                    }`}
                    aria-current={active ? 'page' : undefined}
                  >
                    <Icon size={18} aria-hidden="true" />
                    {item.label}
                  </button>
                );
              })}
            </nav>
            <div className="mt-12 border-t border-line pt-5">
              <div className="flex items-center gap-2 text-xs font-semibold text-ink">
                <Activity size={15} className={serviceReady ? 'text-sage' : 'text-coral'} aria-hidden="true" />
                {serviceReady ? 'Assessment service ready' : 'Check assessment service'}
              </div>
            </div>
          </div>
        </div>
      )}

      <main className="min-h-screen lg:ml-[248px]">
        <div className="mx-auto w-full max-w-[1480px] px-5 py-7 sm:px-8 sm:py-9 lg:px-12 lg:py-12">
          {children}
        </div>
      </main>
    </div>
  );
}
