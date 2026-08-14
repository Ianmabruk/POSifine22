import { Request, Response, NextFunction } from "express";
import jwt from "jsonwebtoken";

export interface JWTPayload {
  id: string;
  role: "admin" | "cashier" | "main_admin";
  plan: "starter" | "business" | "custom";
  accountId: string;
}

export interface AuthRequest extends Request {
  user?: JWTPayload;
  account?: any;
}

export const verifyToken = (
  req: AuthRequest,
  res: Response,
  next: NextFunction
) => {
  const token = req.headers.authorization?.split(" ")[1];

  if (!token) {
    return res.status(401).json({ error: "No token provided" });
  }

  try {
    const secret = process.env.JWT_SECRET;
    if (!secret) {
      return res.status(500).json({ error: "Server misconfigured: JWT_SECRET missing" });
    }

    const decoded = jwt.verify(token, secret) as JWTPayload;

    req.user = decoded;
    next();
  } catch {
    return res.status(401).json({ error: "Invalid token" });
  }
};

// Backwards-compatible exports expected by routes
export const authenticateJWT = verifyToken;

export const authorize = (roles: string[]) => (
  req: AuthRequest,
  res: Response,
  next: NextFunction
) => {
  const userRole = req.user?.role?.toUpperCase();
  if (!userRole || !roles.map((r) => r.toUpperCase()).includes(userRole)) {
    return res.status(403).json({ error: "Forbidden" });
  }
  next();
};

export const requireSuperAdmin = (
  req: AuthRequest,
  res: Response,
  next: NextFunction
) => {
  const userRole = req.user?.role?.toUpperCase();
  if (userRole !== "MAIN_ADMIN" && userRole !== "owner") {
    return res.status(403).json({ error: "Super Admin access required" });
  }
  next();
};