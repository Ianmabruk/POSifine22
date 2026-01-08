import { Request, Response, NextFunction } from "express";
import { AuthService } from "./auth.service";
import { ok } from "../../utils/response";

export const AuthController = {
  async signup(req: Request, res: Response, next: NextFunction) {
    try {
      const { email, password, role, deviceId } = req.body;
      const result = await AuthService.signup(email.toLowerCase(), password, role, deviceId);
      res.status(201).json(ok({ token: result.accessToken, refreshToken: result.refreshToken, user: { id: result.user.id, email: result.user.email, role: result.user.role } }));
    } catch (e) { next(e); }
  },
  async login(req: Request, res: Response, next: NextFunction) {
    try {
      const { email, password, deviceId } = req.body;
      const result = await AuthService.login(email.toLowerCase(), password, deviceId);
      res.json(ok({ token: result.accessToken, refreshToken: result.refreshToken, user: { id: result.user.id, email: result.user.email, role: result.user.role } }));
    } catch (e) { next(e); }
  },
  async refresh(req: Request, res: Response, next: NextFunction) {
    try {
      const { refreshToken, deviceId } = req.body;
      const result = await AuthService.refresh(refreshToken, deviceId);
      res.json(ok(result));
    } catch (e) { next(e); }
  },
  async me(req: Request, res: Response) {
    const user = (req as any).user;
    res.json(ok(user));
  }
};
