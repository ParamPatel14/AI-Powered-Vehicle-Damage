import { useEffect, useMemo, useState } from 'react';
import { AppShell, type AppRoute } from './components/AppShell';
import { ApiError, apiUrl, getAssessment, getHealth } from './services/api';
import type { AssessmentRecord } from './types/assessment';
import { DashboardPage } from './pages/DashboardPage';
import { NewAssessmentPage } from './pages/NewAssessmentPage';
import { HistoryPage } from './pages/HistoryPage';
import { SettingsPage } from './pages/SettingsPage';
import { AssessmentReportPage } from './pages/AssessmentReportPage';
import { NotFoundPage } from './pages/NotFoundPage';

interface LocationState {
  route: AppRoute;
  assessmentId?: string;
}

function parseHash(): LocationState {
  const value = window.location.hash.replace(/^#\/?/, '');
  if (!value || value === 'dashboard') return { route: 'dashboard' };
  if (value === 'assessments/new') return { route: 'new-assessment' };
  if (value === 'assessments/history') return { route: 'history' };
  if (value === 'settings') return { route: 'settings' };
  if (value.startsWith('assessments/')) {
    const assessmentId = decodeURIComponent(value.slice('assessments/'.length));
    if (assessmentId) return { route: 'report', assessmentId };
  }
  return { route: 'not-found' };
}

function writeHash(value: string) {
  window.location.hash = value;
}

export default function App() {
  const [location, setLocation] = useState<LocationState>(() => parseHash());
  const [records, setRecords] = useState<AssessmentRecord[]>([]);
  const [serviceReady, setServiceReady] = useState<boolean | null>(null);
  const [loadingAssessment, setLoadingAssessment] = useState(false);

  useEffect(() => {
    const handleHashChange = () => setLocation(parseHash());
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  useEffect(() => {
    let active = true;
    void getHealth()
      .then((health) => {
        if (active) setServiceReady(health.ready);
      })
      .catch((error) => {
        if (!active) return;
        if (error instanceof ApiError && error.payload && typeof error.payload === 'object' && 'ready' in error.payload) {
          setServiceReady(Boolean(error.payload.ready));
        } else {
          setServiceReady(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const currentRecord = useMemo(
    () => records.find((record) => record.response.assessment_id === location.assessmentId),
    [location.assessmentId, records],
  );

  useEffect(() => {
    if (location.route !== 'report' || !location.assessmentId || currentRecord) return;
    let active = true;
    setLoadingAssessment(true);
    void getAssessment(location.assessmentId).then((response) => {
      if (!active) return;
      const sourceImageUrl = response.artifacts?.source_image_url ? apiUrl(response.artifacts.source_image_url) : undefined;
      setRecords((existing) => existing.some((item) => item.response.assessment_id === response.assessment_id) ? existing : [{
        response,
        previewUrl: sourceImageUrl || '',
        sourceImageUrl,
        annotatedPreviewUrl: response.artifacts?.annotated_preview_url ? apiUrl(response.artifacts.annotated_preview_url) : undefined,
        pdfUrl: response.artifacts?.pdf_url ? apiUrl(response.artifacts.pdf_url) : undefined,
        fileName: response.source_image,
        fileSize: 0,
        createdAt: response.artifact_created_at || new Date().toISOString(),
      }, ...existing]);
    }).catch(() => {
      if (active) setLoadingAssessment(false);
    }).finally(() => { if (active) setLoadingAssessment(false); });
    return () => { active = false; };
  }, [location.route, location.assessmentId, currentRecord]);

  const navigate = (route: Exclude<AppRoute, 'report' | 'not-found'>) => {
    const hashes = {
      dashboard: '#/dashboard',
      'new-assessment': '#/assessments/new',
      history: '#/assessments/history',
      settings: '#/settings',
    } as const;
    writeHash(hashes[route]);
  };

  const openReport = (assessmentId: string) => writeHash(`#/assessments/${encodeURIComponent(assessmentId)}`);

  const handleComplete = (record: AssessmentRecord) => {
    setRecords((existing) => [record, ...existing.filter((item) => item.response.assessment_id !== record.response.assessment_id)]);
    openReport(record.response.assessment_id);
  };

  const handleAssessmentUpdate = (response: AssessmentRecord['response']) => {
    setRecords((existing) => existing.map((item) => item.response.assessment_id === response.assessment_id ? { ...item, response } : item));
  };

  let page: React.ReactNode;
  switch (location.route) {
    case 'new-assessment':
      page = <NewAssessmentPage onComplete={handleComplete} />;
      break;
    case 'history':
      page = <HistoryPage records={records} onNewAssessment={() => navigate('new-assessment')} onOpenAssessment={openReport} />;
      break;
    case 'settings':
      page = <SettingsPage />;
      break;
    case 'report':
      page = currentRecord ? <AssessmentReportPage record={currentRecord} onUpdate={handleAssessmentUpdate} onBack={() => navigate('dashboard')} onNewAssessment={() => navigate('new-assessment')} /> : loadingAssessment ? <div className="panel rounded-xl p-8 text-sm text-muted" role="status">Loading assessment…</div> : <NotFoundPage onDashboard={() => navigate('dashboard')} />;
      break;
    case 'not-found':
      page = <NotFoundPage onDashboard={() => navigate('dashboard')} />;
      break;
    case 'dashboard':
    default:
      page = <DashboardPage records={records} serviceReady={serviceReady} onNewAssessment={() => navigate('new-assessment')} onOpenAssessment={openReport} />;
      break;
  }

  return <AppShell route={location.route} onNavigate={navigate} serviceReady={serviceReady}>{page}</AppShell>;
}
