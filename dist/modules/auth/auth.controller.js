import { AuthService } from "./auth.service";
import { ok } from "../../utils/response";
export const AuthController = {
    async signup(req, res, next) {
        try {
            const { email, password, role, deviceId, deviceMode } = req.body;
            const result = await AuthService.signup(email.toLowerCase(), password, role, deviceId, deviceMode);
            res.status(201).json(ok({ token: result.accessToken, refreshToken: result.refreshToken, user: { id: result.user.id, email: result.user.email, role: result.user.role, deviceMode: result.user.deviceMode } }));
        }
        catch (e) {
            next(e);
        }
    },
    async login(req, res, next) {
        try {
            const { email, password, deviceId } = req.body;
            const result = await AuthService.login(email.toLowerCase(), password, deviceId);
            res.json(ok({ token: result.accessToken, refreshToken: result.refreshToken, user: { id: result.user.id, email: result.user.email, role: result.user.role, deviceMode: result.user.deviceMode } }));
        }
        catch (e) {
            next(e);
        }
    },
    async superAdminLogin(req, res, next) {
        try {
            const { email, password, deviceId } = req.body;
            const result = await AuthService.superAdminLogin(email.toLowerCase(), password, deviceId);
            res.json(ok({ token: result.accessToken, refreshToken: result.refreshToken, user: { id: result.user.id, email: result.user.email, role: result.user.role } }));
        }
        catch (e) {
            next(e);
        }
    },
    async refresh(req, res, next) {
        try {
            const { refreshToken, deviceId } = req.body;
            const result = await AuthService.refresh(refreshToken, deviceId);
            res.json(ok(result));
        }
        catch (e) {
            next(e);
        }
    },
    async me(req, res) {
        try {
            const userId = req.user?.id;
            if (!userId) {
                return res.status(401).json({ error: "Unauthorized" });
            }
            const user = await AuthService.me(userId);
            res.json(ok(user));
        }
        catch (e) {
            return res.status(401).json({ error: "Unauthorized" });
        }
    }
};
