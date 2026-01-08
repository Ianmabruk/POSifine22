import { fail } from "../utils/response";
export function validate(schema) {
    return (req, res, next) => {
        const parsed = schema.safeParse({ body: req.body, query: req.query, params: req.params, headers: req.headers });
        if (!parsed.success) {
            const zerr = parsed.error.flatten();
            return res.status(400).json(fail(400, "VALIDATION_ERROR", "Invalid request", zerr));
        }
        next();
    };
}
