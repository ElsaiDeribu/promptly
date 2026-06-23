/**
 * Generate a unique id, preferring the native crypto API and falling back to a
 * timestamp + random suffix for environments where it is unavailable.
 */
export function makeId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Normalize the many shapes an error can take (string, axios error payload,
 * Error instance) into a single user-facing message.
 */
export function resolveErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'string' && error) return error;

  if (error && typeof error === 'object') {
    const e = error as Record<string, any>;
    return e.error || e.details?.error || e.details?.detail || e.details || e.message || fallback;
  }

  return fallback;
}
