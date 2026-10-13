import { ScanLine } from 'lucide-react';

interface BrandMarkProps {
  compact?: boolean;
}

export function BrandMark({ compact = false }: BrandMarkProps) {
  return (
    <div className="flex items-center gap-3" aria-label="Veyra vehicle assessment">
      <span className="relative flex h-9 w-9 items-center justify-center rounded-[10px] bg-ink text-white shadow-sm">
        <span className="absolute inset-[7px] rounded-[5px] border border-white/35" />
        <ScanLine size={16} strokeWidth={1.8} aria-hidden="true" />
      </span>
      {!compact && (
        <span className="leading-none">
          <span className="block font-display text-[17px] font-bold tracking-[0.11em] text-ink">VEYRA</span>
          <span className="mt-1 block text-[9px] font-semibold uppercase tracking-[0.2em] text-muted">Vehicle assessment</span>
        </span>
      )}
    </div>
  );
}
