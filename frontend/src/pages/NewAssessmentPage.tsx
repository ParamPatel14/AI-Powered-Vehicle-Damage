import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, ArrowRight, Check, FileCheck2, LoaderCircle, LockKeyhole, ScanSearch } from 'lucide-react';
import { apiUrl, assessImage, ApiError } from '../services/api';
import { validateImageDimensions, validateImageFile } from '../lib/uploadValidation';
import type { AssessmentContext, AssessmentRecord } from '../types/assessment';
import { PageHeader } from '../components/PageHeader';
import { UploadDropzone } from '../components/UploadDropzone';
import { AssessmentContextForm } from '../components/AssessmentContextForm';

interface NewAssessmentPageProps {
  onComplete: (record: AssessmentRecord) => void;
}

export function NewAssessmentPage({ onComplete }: NewAssessmentPageProps) {
  const [assessmentContext, setAssessmentContext] = useState<AssessmentContext>({ policy_category: 'unknown', policy_add_ons: [] });
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const previewRef = useRef<string | null>(null);
  const preservePreviewRef = useRef(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (!preservePreviewRef.current && previewRef.current) URL.revokeObjectURL(previewRef.current);
    };
  }, []);

  const removePreview = () => {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = null;
    setPreviewUrl(null);
    setFile(null);
    setValidationError(null);
    setSubmitError(null);
  };

  const selectFile = async (nextFile: File | null) => {
    setSubmitError(null);
    const error = validateImageFile(nextFile);
    if (error || !nextFile) {
      setValidationError(error);
      if (error) {
        if (previewRef.current) URL.revokeObjectURL(previewRef.current);
        previewRef.current = null;
        setPreviewUrl(null);
        setFile(null);
      }
      return;
    }

    setIsValidating(true);
    setValidationError(null);
    const dimensionsError = await validateImageDimensions(nextFile);
    setIsValidating(false);
    if (dimensionsError) {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
      previewRef.current = null;
      setPreviewUrl(null);
      setFile(null);
      setValidationError(dimensionsError);
      return;
    }

    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    const nextPreviewUrl = URL.createObjectURL(nextFile);
    previewRef.current = nextPreviewUrl;
    setPreviewUrl(nextPreviewUrl);
    setFile(nextFile);
  };

  const submit = async () => {
    if (!file || !previewUrl || isSubmitting || isValidating) return;
    setSubmitError(null);
    setIsSubmitting(true);
    try {
      const response = await assessImage(file, assessmentContext);
      preservePreviewRef.current = true;
      onComplete({
        response,
        previewUrl,
        fileName: file.name,
        fileSize: file.size,
        createdAt: new Date().toISOString(),
        sourceImageUrl: response.artifacts?.source_image_url ? apiUrl(response.artifacts.source_image_url) : undefined,
        annotatedPreviewUrl: response.artifacts?.annotated_preview_url ? apiUrl(response.artifacts.annotated_preview_url) : undefined,
        pdfUrl: response.artifacts?.pdf_url ? apiUrl(response.artifacts.pdf_url) : undefined,
      });
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.message : 'The assessment could not be completed. Try again.');
      setIsSubmitting(false);
    }
  };

  return (
    <div className="motion-enter">
      <PageHeader
        eyebrow="New assessment"
        title="Bring the evidence."
        description="Upload one vehicle image and let the connected service assemble a provisional damage report for review."
      />

      <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <section className="panel rounded-[16px] p-4 sm:p-6" aria-labelledby="upload-heading">
          <div className="mb-5 flex items-center justify-between gap-4 px-1">
            <div>
              <p className="eyebrow">Step 01 / Source image</p>
              <h2 id="upload-heading" className="mt-2 font-display text-xl font-semibold tracking-[-0.025em]">Stage a vehicle image</h2>
            </div>
            {isValidating && <span className="inline-flex items-center gap-2 text-xs font-semibold text-muted"><LoaderCircle size={15} className="animate-spin text-accent" aria-hidden="true" /> Checking image</span>}
          </div>
          <UploadDropzone
            file={file}
            previewUrl={previewUrl}
            onFileSelected={selectFile}
            onRemove={removePreview}
            disabled={isSubmitting || isValidating}
            error={validationError}
          />
          <AssessmentContextForm value={assessmentContext} onChange={setAssessmentContext} />
          {submitError && (
            <div className="mt-5 flex items-start gap-3 rounded-[11px] border border-coral/20 bg-coral-soft/55 p-4" role="alert">
              <AlertTriangle size={17} className="mt-0.5 shrink-0 text-coral" aria-hidden="true" />
              <div><p className="text-sm font-semibold text-coral">Analysis could not be completed</p><p className="mt-1 text-xs leading-5 text-[#86463d]">{submitError}</p></div>
            </div>
          )}
          <div className="mt-6 flex flex-col-reverse gap-3 border-t border-line pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="flex items-start gap-2 text-xs leading-5 text-muted"><LockKeyhole size={14} className="mt-0.5 shrink-0" aria-hidden="true" />Detection does not call Gemini. Optional vehicle details can improve context but are not required. Choosing Calculate Repair Cost later sends the saved image and findings to Gemini; an estimate may still be unavailable when evidence is insufficient.</p>
            <button type="button" className="button-primary shrink-0" onClick={submit} disabled={!file || !previewUrl || isSubmitting || isValidating} aria-busy={isSubmitting}>
              {isSubmitting ? <><span className="loading-spinner" aria-hidden="true" /> Analyzing…</> : <><ScanSearch size={17} aria-hidden="true" /> Analyze vehicle <ArrowRight size={15} aria-hidden="true" /></>}
            </button>
          </div>
          {isSubmitting && <ProcessingNotice />}
        </section>

        <aside className="space-y-5">
          <div className="panel rounded-[16px] p-5 sm:p-6">
            <p className="eyebrow">Before you submit</p>
            <h2 className="mt-2 font-display text-xl font-semibold tracking-[-0.025em]">A stronger image makes a clearer read.</h2>
            <ul className="mt-5 space-y-4 text-sm leading-6 text-muted">
              <Guidance icon={<Check size={15} />} text="Use a well-lit view with the damaged area visible." />
              <Guidance icon={<Check size={15} />} text="Keep the vehicle in focus and avoid heavy glare." />
              <Guidance icon={<Check size={15} />} text="One JPEG or PNG image is accepted per assessment." />
            </ul>
          </div>
          <div className="rounded-[16px] border border-accent/15 bg-accent-soft/45 p-5 sm:p-6">
            <div className="flex items-start gap-3"><FileCheck2 size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" /><div><p className="text-sm font-semibold text-ink">What the report can say</p><p className="mt-2 text-xs leading-5 text-muted">Image analysis returns detected classes, confidence, bounding regions, segmentation evidence, provisional severity, and review flags. Summary and cost estimates are separate actions after detection.</p></div></div>
            <p className="mt-4 border-t border-accent/15 pt-4 text-[11px] leading-5 text-accent-dark">It cannot confirm hidden damage, exact vehicle components, roadworthiness, a repair method, or a guaranteed quotation.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Guidance({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <li className="flex items-start gap-3"><span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-sage-soft text-sage">{icon}</span><span>{text}</span></li>;
}

function ProcessingNotice() {
  return (
    <div className="mt-5 rounded-[11px] border border-accent/15 bg-accent-soft/35 px-4 py-3" role="status" aria-live="polite">
      <div className="flex items-center gap-3"><LoaderCircle size={17} className="animate-spin text-accent" aria-hidden="true" /><p className="text-sm font-semibold text-ink">Assembling your assessment</p></div>
      <p className="mt-2 pl-7 text-xs leading-5 text-muted">The detector is analyzing the image and preparing preliminary severity and review flags. Gemini is not called during this step.</p>
    </div>
  );
}
