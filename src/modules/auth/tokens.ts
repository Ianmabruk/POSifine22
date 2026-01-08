import jwt from "jsonwebtoken";
import { env } from "../../config/env";

export function issueAccessToken(payload: Record<string, any>) {
  const j: any = jwt as any;
  return j.sign(payload, env.JWT_SECRET, { expiresIn: env.JWT_EXPIRES_IN });
}

export function issueRefreshToken(payload: Record<string, any>) {
  const j: any = jwt as any;
  return j.sign(payload, env.REFRESH_TOKEN_SECRET, { expiresIn: env.REFRESH_TOKEN_EXPIRES_IN });
}

export function verifyRefreshToken(token: string) {
  const j: any = jwt as any;
  return j.verify(token, env.REFRESH_TOKEN_SECRET) as any;
}
