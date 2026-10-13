import { useRef, useState } from 'react';
import { CheckCircle2, FileImage, ImagePlus, RefreshCw, Trash2, UploadCloud } from 'lucide-react';
import { formatBytes, MAX_UPLOAD_BYTES } from '../lib/uploadValidation';

interface UploadDropzoneProps {
  file: File | null;
  previewUrl: string | null;
  onFileSelected: (file: File | null) => void;
  onRemove: () => void;
  disabled?: boolean;
  error?: string | null;
}

export function UploadDropzone({
  file,
  previewUrl,
  onFileSelected,
  onRemove,
  disabled = false,
  error,
}: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleFiles = (files: FileList | null) => {
    if (disabled || !files?.length) return;
    onFileSelected(files[0]);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (disabled || file) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      inputRef.current?.click();
    }
  };

  return (
    <div>
      <div
        className={`relative overflow-hidden rounded-[16px] border transition duration-200 ${
          error ? 'border-coral bg-coral-soft/25' : isDragging ? 'border-accent bg-accent-soft/55' : 'border-line bg-white/70'
        } ${disabled ? 'opacity-70' : ''}`}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!disabled) setIsDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (event.currentTarget === event.target) setIsDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          handleFiles(event.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          className="sr-only"
          type="file"
          accept="image/jpeg,image/png,.jpg,.jpeg,.png"
          onChange={(event) => {
            handleFiles(event.target.files);
            event.currentTarget.value = '';
          }}
          disabled={disabled}
          aria-label="Choose a vehicle image"
        />

        {!file || !previewUrl ? (
          <div
            className="mesh-lines flex min-h-[340px] flex-col items-center justify-center px-6 py-12 text-center"
            role="button"
            tabIndex={disabled ? -1 : 0}
            onClick={() => !disabled && inputRef.current?.click()}
            onKeyDown={handleKeyDown}
            aria-label="Upload a vehicle image"
          >
            <span className={`flex h-16 w-16 items-center justify-center rounded-[18px] border bg-panel shadow-sm transition ${isDragging ? 'border-accent text-accent' : 'border-line text-muted'}`}>
              {isDragging ? <UploadCloud size={28} strokeWidth={1.6} aria-hidden="true" /> : <ImagePlus size={28} strokeWidth={1.6} aria-hidden="true" />}
            </span>
            <p className="mt-6 font-display text-lg font-semibold tracking-[-0.02em] text-ink">{isDragging ? 'Release to stage this image' : 'Drop a vehicle image here'}</p>
            <p className="mt-2 max-w-sm text-sm leading-6 text-muted">Or choose a file from your device. Use a clear view of the vehicle for the strongest image-based readout.</p>
            <button type="button" className="button-secondary mt-6" onClick={(event) => { event.stopPropagation(); inputRef.current?.click(); }} disabled={disabled}>
              <FileImage size={16} aria-hidden="true" />
              Choose image
            </button>
            <p className="mt-5 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">JPEG or PNG · up to {formatBytes(MAX_UPLOAD_BYTES)}</p>
          </div>
        ) : (
          <div className="p-4 sm:p-5">
            <div className="relative overflow-hidden rounded-[11px] border border-line bg-ink">
              <img src={previewUrl} alt={`Selected vehicle image: ${file.name}`} className="mx-auto max-h-[430px] w-full object-contain" />
              <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-4 bg-gradient-to-t from-ink/85 via-ink/35 to-transparent px-4 pb-4 pt-12 text-white">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{file.name}</p>
                  <p className="mt-1 text-xs text-white/70">{formatBytes(file.size)} · Ready to analyze</p>
                </div>
                <CheckCircle2 className="shrink-0 text-[#a9d3c0]" size={20} aria-hidden="true" />
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs leading-5 text-muted">The uploaded file is sent to the connected assessment API only when you select Analyze vehicle.</p>
              <div className="flex items-center gap-2">
                <button type="button" className="button-quiet" onClick={() => inputRef.current?.click()} disabled={disabled}>
                  <RefreshCw size={15} aria-hidden="true" />
                  Replace
                </button>
                <button type="button" className="button-quiet text-coral hover:bg-coral-soft hover:text-coral" onClick={onRemove} disabled={disabled}>
                  <Trash2 size={15} aria-hidden="true" />
                  Remove
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
      {error && <p className="mt-3 text-sm font-semibold text-coral" role="alert">{error}</p>}
    </div>
  );
}
