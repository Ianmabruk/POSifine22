import { Request, Response, NextFunction } from "express";

export interface AuthRequest extends Request {
  user?: {
    id: string;
    role: "admin" | "cashier";
    plan: "basic" | "ultra";
    accountId: string;
  };
}

export const requireUltra = (
  req: AuthRequest,
  res: Response,
  next: NextFunction
) => {
  if (req.user?.plan !== "ultra") {
    return res.status(403).json({
      success: false,
      error: "Ultra subscription required"
    });
  }
  next();
};

export const requireAdmin = (
  req: AuthRequest,
  res: Response,
  next: NextFunction
) => {
  if (req.user?.role !== "admin") {
    return res.status(403).json({
      success: false,
      error: "Admin access only"
    });
  }
  next();
};
