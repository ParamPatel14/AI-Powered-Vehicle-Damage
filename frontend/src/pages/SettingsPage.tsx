import { useCallback, useEffect, useState } from 'react';
import { BookOpen, CheckCircle2, CircleAlert, Cpu, FileImage, History, Info, RefreshCw, ServerCog, ShieldCheck } from 'lucide-react';
import { API_BASE_URL, ApiError, getHealth, isHealthResponse, runGeminiDiagnostic } from '../services/api';
import type { HealthResponse } from '../types/assessment';
import { PageHeader } from '../components/PageHeader';
import { LoadingState } from '../components/LoadingState';
import { ServiceBadge, StatusBadge } from '../components/StatusBadge';

export function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [geminiDiagnostic, setGeminiDiagnostic] = useState<{ status: string; category: string; model?: string; message: string } | null>(null);
  const [diagnosticRunning, setDiagnosticRunning] = useState(false);

  const loadHealth = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setHealth(await getHealth());
    } catch (reason) {
      if (reason instanceof ApiError && isHealthResponse(reason.payload)) {
        setHealth(reason.payload);
        setError('The API is reachable, but one or more required components are not ready.');
      } else {
        setHealth(null);
        setError(reason instanceof ApiError ? reason.message : 'The health check could not be completed.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHealth();
  }, [loadHealth]);

  const docsHref = API_BASE_URL ? `${API_BASE_URL.replace(/\/$/, '')}/docs` : 'http://127.0.0.1:8000/docs';
  const testGemini = async () => {
    if (diagnosticRunning) return;
    setDiagnosticRunning(true);
    setGeminiDiagnostic(null);
    try { setGeminiDiagnostic(await runGeminiDiagnostic()); }
    catch (reason) { setGeminiDiagnostic({ status: 'failed', category: 'request_error', message: reason instanceof Error ? reason.message : 'Gemini diagnostic request failed.' }); }
    finally { setDiagnosticRunning(false); }
  };

  return (
    <div className="motion-enter">
      <PageHeader eyebrow="Settings" title="Know the service boundary." description="Connectivity and safe operational details for the current assessment workspace." />

      <section className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
        <div className="panel overflow-hidden rounded-[16px]">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
            <div><p className="eyebrow">Backend connectivity</p><h2 className="mt-1 font-display text-xl font-semibold tracking-[-0.025em]">Assessment service</h2></div>
            <div className="flex items-center gap-3"><ServiceBadge ready={health?.ready ?? (loading ? null : false)} /><button type="button" className="button-quiet border border-line bg-white/70" onClick={() => void loadHealth()} disabled={loading}><RefreshCw size={15} className={loading ? 'animate-spin' : ''} aria-hidden="true" /> Refresh</button></div>
          </div>
          {loading && <LoadingState label="Checking /health…" />}
          {!loading && health && (
            <div className="p-5 sm:p-6">
              <div className={`flex items-start gap-3 rounded-[11px] border p-4 ${health.ready ? 'border-sage/20 bg-sage-soft/55' : 'border-amber/20 bg-amber-soft/55'}`}>
                {health.ready ? <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-sage" aria-hidden="true" /> : <CircleAlert size={18} className="mt-0.5 shrink-0 text-amber" aria-hidden="true" />}
                <div><p className="text-sm font-semibold text-ink">{health.ready ? 'All required components are ready' : 'The service is reachable but not ready'}</p><p className="mt-1 text-xs leading-5 text-muted">{error || 'The response came from the live /health endpoint.'}</p></div>
              </div>
              <div className="mt-6 divide-y divide-line border-y border-line">
                <HealthRow icon={<ServerCog size={17} />} label="API" value={health.api === 'running' ? 'Running' : health.api} ready={health.api === 'running'} error={null} />
                <HealthRow icon={<Cpu size={17} />} label="Detection model" value={health.model.available ? 'Available' : 'Unavailable'} ready={health.model.available} error={health.model.error} />
                <HealthRow icon={<ShieldCheck size={17} />} label="Pricing configuration" value={health.pricing_configuration.available ? 'Available' : 'Unavailable'} ready={health.pricing_configuration.available} error={health.pricing_configuration.error} />
                {health.gemini && <HealthRow icon={<SparklesIcon />} label="Gemini assessment" value={health.gemini.status === 'configured' ? 'Configured' : health.gemini.status === 'disabled' ? 'Disabled' : 'Unavailable'} ready={health.gemini.status === 'configured' || health.gemini.status === 'disabled'} error={health.gemini.model ? health.gemini.model : null} />}
              </div>
              <p className="mt-5 text-xs leading-5 text-muted">The health response exposes availability and safe error codes only. It does not contact Gemini. Clicking Calculate Repair Cost sends the saved source image and detector evidence to Gemini; Generate AI Summary sends structured detector evidence only.</p>
            </div>
          )}
          {!loading && !health && (
            <div className="p-5 sm:p-6"><div className="rounded-[11px] border border-coral/20 bg-coral-soft/55 p-4"><div className="flex items-start gap-3"><CircleAlert size={18} className="mt-0.5 shrink-0 text-coral" aria-hidden="true" /><div><p className="text-sm font-semibold text-coral">Could not connect to the backend</p><p className="mt-1 text-xs leading-5 text-[#86463d]">{error}</p></div></div></div><button type="button" className="button-secondary mt-5" onClick={() => void loadHealth()}><RefreshCw size={15} aria-hidden="true" /> Try again</button></div>
          )}
        </div>

        <div className="space-y-5">
          <div className="panel rounded-[16px] p-5 sm:p-6">
            <p className="eyebrow">Gemini live verification</p>
            <h2 className="mt-2 font-display text-xl font-semibold tracking-[-0.025em]">Test provider connection</h2>
            <p className="mt-2 text-xs leading-5 text-muted">This button sends one minimal structured request to the configured Gemini model. Health checks and image detection never call Gemini.</p>
            <button type="button" className="button-secondary mt-4" onClick={() => void testGemini()} disabled={diagnosticRunning}><SparklesIcon />{diagnosticRunning ? 'Testing Gemini…' : 'Test Gemini connection'}</button>
            {geminiDiagnostic && <div className={`mt-4 rounded-[10px] border p-3 ${geminiDiagnostic.status === 'success' ? 'border-sage/20 bg-sage-soft/45' : 'border-amber/20 bg-amber-soft/45'}`} role="status"><p className="text-xs font-semibold text-ink">{geminiDiagnostic.status === 'success' ? 'Live Gemini request succeeded' : `Gemini: ${geminiDiagnostic.category.replaceAll('_', ' ')}`}</p><p className="mt-1 text-xs leading-5 text-muted">{geminiDiagnostic.message}</p>{geminiDiagnostic.model && <p className="mt-1 text-[11px] text-muted">Model: {geminiDiagnostic.model}</p>}</div>}
          </div>
          <div className="panel rounded-[16px] p-5 sm:p-6">
            <p className="eyebrow">Application configuration</p>
            <h2 className="mt-2 font-display text-xl font-semibold tracking-[-0.025em]">Assessment limits</h2>
            <div className="mt-5 space-y-3">
              <ConfigRow label="Accepted images" value="JPEG, PNG" />
              <ConfigRow label="Maximum upload" value="10 MiB" />
              <ConfigRow label="Maximum image size" value="40 megapixels" />
              <ConfigRow label="Request type" value="Synchronous analysis" />
            </div>
            <p className="mt-5 border-t border-line pt-4 text-[11px] leading-5 text-muted">These constraints mirror the validation constants in the existing FastAPI endpoint.</p>
          </div>
          <div className="rounded-[16px] border border-accent/15 bg-accent-soft/45 p-5 sm:p-6">
            <div className="flex items-start gap-3"><BookOpen size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" /><div><p className="text-sm font-semibold text-ink">API documentation</p><p className="mt-1 text-xs leading-5 text-muted">Open the live FastAPI documentation to inspect the available request and response contract.</p><a className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-accent-dark underline decoration-accent/30 underline-offset-4 hover:decoration-accent" href={docsHref} target="_blank" rel="noreferrer">Open /docs <BookOpen size={13} aria-hidden="true" /></a></div></div>
          </div>
        </div>
      </section>

      <section className="mt-8 grid gap-5 md:grid-cols-3" aria-label="Current service capabilities">
        <BoundaryCard icon={<FileImage size={18} />} title="Annotated previews" text="Not available from the current API. Reports identify this clearly and never present the original image as an annotated file." />
        <BoundaryCard icon={<History size={18} />} title="Durable history" text="Not exposed by the backend. The frontend keeps completed reports in the current session only." />
        <BoundaryCard icon={<Info size={18} />} title="Preliminary outputs" text="Severity and cost sections preserve their provisional labels, assumptions, review flags, and disclaimers." />
      </section>
    </div>
  );
}

function HealthRow({ icon, label, value, ready, error }: { icon: React.ReactNode; label: string; value: string; ready: boolean; error: string | null }) {
  return <div className="flex items-center justify-between gap-4 py-4"><div className="flex min-w-0 items-center gap-3 text-sm text-muted"><span className="text-accent">{icon}</span><span>{label}</span></div><div className="flex shrink-0 items-center gap-3"><StatusBadge label={value} tone={ready ? 'success' : 'danger'} />{error && <span className="hidden text-[11px] text-muted sm:inline">{error}</span>}</div></div>;
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-4 rounded-[9px] bg-canvas/55 px-3 py-2.5 text-sm"><span className="text-muted">{label}</span><span className="font-semibold text-ink">{value}</span></div>;
}

function BoundaryCard({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div className="panel rounded-[14px] p-5"><span className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-accent-soft text-accent">{icon}</span><h3 className="mt-4 text-sm font-semibold text-ink">{title}</h3><p className="mt-2 text-xs leading-5 text-muted">{text}</p></div>;
}

function SparklesIcon() {
  return <span className="text-[12px] font-bold" aria-hidden="true">AI</span>;
}
