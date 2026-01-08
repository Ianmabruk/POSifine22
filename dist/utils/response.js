export function ok(data, meta) {
    return { success: true, data, ...(meta ? { meta } : {}) };
}
export function fail(status, code, message, details) {
    return { success: false, error: { code, message, ...(details ? { details } : {}) } };
}
