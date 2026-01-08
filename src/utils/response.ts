export function ok(data: unknown, meta?: unknown) {
  return { success: true, data, ...(meta ? { meta } : {}) };
}
export function fail(status: number, code: string, message: string, details?: unknown) {
  return { success: false, error: { code, message, ...(details ? { details } : {}) } };
}
