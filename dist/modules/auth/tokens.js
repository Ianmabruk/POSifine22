import jwt from "jsonwebtoken";
import { env } from "../../config/env";
export function issueAccessToken(payload) {
    const j = jwt;
    return j.sign(payload, env.JWT_SECRET, { expiresIn: env.JWT_EXPIRES_IN });
}
export function issueRefreshToken(payload) {
    const j = jwt;
    return j.sign(payload, env.REFRESH_TOKEN_SECRET, { expiresIn: env.REFRESH_TOKEN_EXPIRES_IN });
}
export function verifyRefreshToken(token) {
    const j = jwt;
    return j.verify(token, env.REFRESH_TOKEN_SECRET);
}
