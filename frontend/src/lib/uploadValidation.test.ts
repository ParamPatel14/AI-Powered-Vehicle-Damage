import { describe, expect, it } from 'vitest';
import { MAX_UPLOAD_BYTES, validateImageFile } from './uploadValidation';

function file(size: number, type: string) {
  return new File([new Uint8Array(size)], 'vehicle.png', { type });
}

describe('validateImageFile', () => {
  it('accepts a non-empty JPEG or PNG below the backend size limit', () => {
    expect(validateImageFile(file(1024, 'image/jpeg'))).toBeNull();
    expect(validateImageFile(file(MAX_UPLOAD_BYTES, 'image/png'))).toBeNull();
  });

  it('rejects unsupported media types', () => {
    expect(validateImageFile(file(1024, 'image/webp'))).toContain('not supported');
  });

  it('rejects empty and oversized files', () => {
    expect(validateImageFile(file(0, 'image/png'))).toContain('empty');
    expect(validateImageFile(file(MAX_UPLOAD_BYTES + 1, 'image/png'))).toContain('upload limit');
  });

  it('requires a file', () => {
    expect(validateImageFile(null)).toContain('Choose');
  });
});
