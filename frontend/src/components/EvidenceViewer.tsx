import { useState } from 'react';
import { ImageOff, Layers3, Maximize2, ScanLine } from 'lucide-react';
import type { AssessmentResponse } from '../types/assessment';
import { formatClassName } from '../lib/formatters';

interface EvidenceViewerProps {
  response: AssessmentResponse;
  imageUrl: string;
  sourceImageUrl?: string;
  annotatedImageUrl?: string;
  fileName: string;
  selectedId: number | null;
  onSelectFinding: (detectionId: number) => void;
}

export function EvidenceViewer({ response, imageUrl, sourceImageUrl, annotatedImageUrl, fileName, selectedId, onSelectFinding }: EvidenceViewerProps) {
  const [showGeometry, setShowGeometry] = useState(true);
  const [view, setView] = useState<'source' | 'annotated'>(annotatedImageUrl ? 'annotated' : 'source');
  const report = response.detection_report;
  const width = report.image_width || 1;
  const height = report.image_height || 1;
  const hasGeometry = report.detections.length > 0 && width > 1 && height > 1;
  const showingAnnotated = view === 'annotated' && Boolean(annotatedImageUrl);
  const displayUrl = showingAnnotated ? annotatedImageUrl : sourceImageUrl || imageUrl;

  return (
    <section className="panel overflow-hidden rounded-[16px]" aria-labelledby="evidence-heading">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4 sm:px-6">
        <div>
          <p className="eyebrow">Visual evidence</p>
          <h2 id="evidence-heading" className="mt-1 font-display text-lg font-semibold tracking-[-0.02em]">Source image & finding map</h2>
        </div>
        {hasGeometry && (
          <button type="button" className="button-quiet border border-line bg-white/70" onClick={() => setShowGeometry((value) => !value)} aria-pressed={showGeometry} disabled={showingAnnotated}>
            <Layers3 size={15} aria-hidden="true" />
            {showingAnnotated ? 'Detector preview selected' : showGeometry ? 'Hide finding map' : 'Show finding map'}
          </button>
        )}
      </div>

      <div className="bg-[#e9e7e0] p-4 sm:p-6">
        <div className="relative mx-auto max-w-[920px] overflow-hidden rounded-[11px] bg-ink shadow-sm" style={{ aspectRatio: `${width} / ${height}` }}>
          {displayUrl ? (
            <img src={displayUrl} alt={`${showingAnnotated ? 'Annotated detector preview' : 'Uploaded vehicle image'}: ${fileName}`} className="absolute inset-0 h-full w-full object-contain" />
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-white/70">
              <ImageOff size={28} aria-hidden="true" />
              <p className="text-sm">Source image is no longer available in this session.</p>
            </div>
          )}

          {!showingAnnotated && showGeometry && hasGeometry && (
            <svg className="absolute inset-0 h-full w-full" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label="Finding geometry reconstructed from the assessment response">
              {report.detections.map((detection, index) => {
                const [x1 = 0, y1 = 0, x2 = 0, y2 = 0] = detection.bbox_xyxy;
                const boxWidth = Math.max(1, x2 - x1);
                const boxHeight = Math.max(1, y2 - y1);
                const isSelected = selectedId === detection.detection_id;
                const color = isSelected ? '#f5bc67' : index % 2 === 0 ? '#8bb8ce' : '#d78c73';
                const polygonPoints = detection.polygons_xy[0]?.map(([x, y]) => `${x},${y}`).join(' ');
                return (
                  <g key={`${detection.detection_id}-${index}`} onClick={() => onSelectFinding(detection.detection_id)} className="cursor-pointer">
                    {polygonPoints && <polygon points={polygonPoints} fill={color} fillOpacity={isSelected ? 0.23 : 0.1} stroke={color} strokeWidth={Math.max(width, height) / 500} strokeOpacity={isSelected ? 0.95 : 0.6} />}
                    <rect x={x1} y={y1} width={boxWidth} height={boxHeight} fill="none" stroke={color} strokeWidth={Math.max(width, height) / (isSelected ? 170 : 260)} strokeDasharray={isSelected ? undefined : '8 6'} />
                    <g transform={`translate(${Math.max(0, x1)}, ${Math.max(15, y1 - 5)})`}>
                      <rect width={Math.max(64, formatClassName(detection.class_name).length * 7 + 26)} height="20" rx="4" fill={color} fillOpacity="0.94" />
                      <text x="8" y="14" fill="#20282e" fontSize={Math.max(9, Math.min(14, width / 55))} fontWeight="700">{index + 1} · {formatClassName(detection.class_name)}</text>
                    </g>
                  </g>
                );
              })}
            </svg>
          )}
          {!hasGeometry && !showingAnnotated && (
            <div className="absolute left-4 top-4 inline-flex items-center gap-2 rounded-full border border-white/20 bg-ink/70 px-3 py-1.5 text-[11px] font-semibold text-white/90 backdrop-blur">
              <ScanLine size={13} aria-hidden="true" /> No finding geometry returned
            </div>
          )}
          <div className="absolute right-3 top-3 hidden rounded-full border border-white/20 bg-ink/65 p-2 text-white/80 backdrop-blur sm:block" title="Finding geometry is interactive">
            <Maximize2 size={14} aria-hidden="true" />
          </div>
        </div>
      </div>

      <div className="space-y-3 px-5 py-4 sm:px-6">
        {annotatedImageUrl && (
          <div className="flex items-center gap-1 rounded-[9px] border border-line bg-canvas/45 p-1" role="tablist" aria-label="Evidence view">
            <button type="button" role="tab" aria-selected={view === 'source'} className={`flex-1 rounded-[7px] px-3 py-2 text-xs font-semibold transition ${view === 'source' ? 'bg-panel text-ink shadow-sm' : 'text-muted hover:text-ink'}`} onClick={() => setView('source')}>Source + reconstructed map</button>
            <button type="button" role="tab" aria-selected={view === 'annotated'} className={`flex-1 rounded-[7px] px-3 py-2 text-xs font-semibold transition ${view === 'annotated' ? 'bg-panel text-ink shadow-sm' : 'text-muted hover:text-ink'}`} onClick={() => setView('annotated')}>Detector-generated preview</button>
          </div>
        )}
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
            <ScanLine size={14} aria-hidden="true" />
          </span>
          <p className="text-xs leading-5 text-muted">
            {showingAnnotated ? 'This is the detector-generated preview returned by the backend. Its labels and masks are original detector evidence; it does not establish a component, hidden damage or roadworthiness.' : annotatedImageUrl ? 'The source view is paired with a reconstructed finding map from returned boxes and polygons. Switch to the detector-generated preview to see the server-created annotated artifact.' : 'The backend did not return an annotated preview artifact; the finding map above is reconstructed from returned bounding boxes and segmentation polygons.'}
          </p>
        </div>
        {hasGeometry && (
          <div className="flex flex-wrap gap-x-4 gap-y-2 border-t border-line pt-3 text-[11px] font-semibold text-muted">
            {report.detections.map((detection, index) => (
              <button key={`${detection.detection_id}-legend`} type="button" className={`inline-flex items-center gap-2 rounded-md px-1.5 py-1 transition hover:bg-canvas ${selectedId === detection.detection_id ? 'bg-canvas text-ink' : ''}`} onClick={() => onSelectFinding(detection.detection_id)}>
                <span className={`h-2 w-2 rounded-full ${index % 2 === 0 ? 'bg-[#8bb8ce]' : 'bg-[#d78c73]'}`} />
                {index + 1} · {formatClassName(detection.class_name)}
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
