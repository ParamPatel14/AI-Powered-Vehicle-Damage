import type { PreliminarySeverity } from '../types/assessment';

export function formatConfidence(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'Unavailable';
  return `${Math.round(value * 100)}%`;
}

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Date unavailable';
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

export function formatClassName(value: string | null | undefined): string {
  if (!value) return 'Unclassified finding';
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatSeverity(value: PreliminarySeverity | null | undefined): string {
  if (!value) return 'Undetermined';
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function formatCurrency(
  value: number | null | undefined,
  currency: string | null | undefined,
): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'Not provided';
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency || 'USD',
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${currency || 'USD'} ${value.toFixed(0)}`;
  }
}

export function formatRange(
  low: number | null | undefined,
  high: number | null | undefined,
  currency: string | null | undefined,
): string {
  if (typeof low !== 'number' || typeof high !== 'number') return 'Not provided';
  return `${formatCurrency(low, currency)} – ${formatCurrency(high, currency)}`;
}

export function compactId(value: string): string {
  if (value.length <= 14) return value;
  return `${value.slice(0, 8)}…${value.slice(-4)}`;
}
