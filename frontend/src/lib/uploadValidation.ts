export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const MAX_IMAGE_PIXELS = 40_000_000;
export const SUPPORTED_MIME_TYPES = ['image/jpeg', 'image/png'] as const;

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(bytes % (1024 * 1024) === 0 ? 0 : 1)} MB`;
}

export function validateImageFile(file: File | null | undefined): string | null {
  if (!file) return 'Choose a JPEG or PNG image to continue.';
  if (!SUPPORTED_MIME_TYPES.includes(file.type as (typeof SUPPORTED_MIME_TYPES)[number])) {
    return 'That file type is not supported. Choose a JPEG or PNG image.';
  }
  if (file.size === 0) return 'This image is empty. Choose another file.';
  if (file.size > MAX_UPLOAD_BYTES) {
    return `This image is larger than the ${formatBytes(MAX_UPLOAD_BYTES)} upload limit.`;
  }
  return null;
}

/** Check the same image-pixel ceiling enforced by the FastAPI service. */
export function validateImageDimensions(file: File): Promise<string | null> {
  return new Promise((resolve) => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      const pixels = image.naturalWidth * image.naturalHeight;
      resolve(
        pixels > MAX_IMAGE_PIXELS
          ? 'This image exceeds the supported 40 megapixel dimension limit.'
          : null,
      );
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      resolve('This image could not be read. Choose a valid JPEG or PNG image.');
    };
    image.src = objectUrl;
  });
}
