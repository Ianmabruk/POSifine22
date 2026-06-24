import { Request, Response, NextFunction } from "express";

export interface AuthRequest extends Request {
  user?: {
    id: string;
    role: "admin" | "cashier" | "main_admin";
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
  if (req.user?.role !== "admin" && req.user?.role !== "main_admin") {
    return res.status(403).json({
      success: false,
      error: "Admin access only"
    });
  }
  next();
};

export const requireSuperAdmin = (
  req: AuthRequest,
  res: Response,
  next: NextFunction
) => {
  if (req.user?.role !== "main_admin") {
    return res.status(403).json({
      success: false,
      error: "Super Admin access required"
    });
  }
  next();
};
