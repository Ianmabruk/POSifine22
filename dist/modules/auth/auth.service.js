import { UsersRepo } from "./users.repository";
import { SessionsRepo } from "./sessions.repository";
import { hashPassword, comparePassword } from "./password";
import { issueAccessToken, issueRefreshToken, verifyRefreshToken } from "./tokens";
import { AppError } from "../../utils/errors";
export const AuthService = {
    async signup(email, password, role, deviceId) {
        const existing = await UsersRepo.findByEmail(email);
        if (existing)
            throw new AppError(409, "EMAIL_TAKEN", "Email already registered");
        const passwordHash = await hashPassword(password);
        const user = await UsersRepo.create({ email, passwordHash, role });
        // Create BASIC active subscription on first signup (single-tenant assumption)
        // Could be extended for multi-tenant later
        const accessToken = issueAccessToken({ id: user.id, role: user.role, plan: "BASIC" });
        const refreshToken = issueRefreshToken({ id: user.id, deviceId });
        const refreshTokenHash = await hashPassword(refreshToken);
        const expiresAt = new Date(Date.now() + 30 * 24 * 3600 * 1000);
        await SessionsRepo.create({ userId: user.id, deviceId, refreshTokenHash, expiresAt });
        return { user, accessToken, refreshToken };
    },
    async login(email, password, deviceId) {
        const user = await UsersRepo.findByEmail(email);
        if (!user)
            throw new AppError(401, "INVALID_CREDENTIALS", "Invalid credentials");
        const ok = await comparePassword(password, user.passwordHash);
        if (!ok)
            throw new AppError(401, "INVALID_CREDENTIALS", "Invalid credentials");
        await UsersRepo.updateLogin(user.id);
        const accessToken = issueAccessToken({ id: user.id, role: user.role, plan: "BASIC" });
        const refreshToken = issueRefreshToken({ id: user.id, deviceId });
        const refreshTokenHash = await hashPassword(refreshToken);
        const existing = await SessionsRepo.findByUserAndDevice(user.id, deviceId);
        if (existing)
            await SessionsRepo.revoke(existing.id);
        const expiresAt = new Date(Date.now() + 30 * 24 * 3600 * 1000);
        await SessionsRepo.create({ userId: user.id, deviceId, refreshTokenHash, expiresAt });
        return { user, accessToken, refreshToken };
    },
    async superAdminLogin(email, password, deviceId) {
        // Check if this is a super admin (main admin) login
        const mainAdminEmail = process.env.MAIN_ADMIN_EMAIL;
        const mainAdminPassword = process.env.MAIN_ADMIN_PASSWORD;
        if (!mainAdminEmail || !mainAdminPassword) {
            throw new AppError(500, "CONFIG_ERROR", "Super admin configuration missing");
        }
        if (email.toLowerCase() !== mainAdminEmail.toLowerCase()) {
            throw new AppError(401, "INVALID_CREDENTIALS", "Invalid credentials");
        }
        const passwordOk = await comparePassword(password, mainAdminPassword);
        if (!passwordOk) {
            throw new AppError(401, "INVALID_CREDENTIALS", "Invalid credentials");
        }
        // Create a super admin user record or use a special ID
        const superAdminId = "main_admin_" + Date.now();
        const accessToken = issueAccessToken({ id: superAdminId, role: "main_admin", plan: "business" });
        const refreshTokenVal = issueRefreshToken({ id: superAdminId, deviceId });
        const refreshTokenHash = await hashPassword(refreshTokenVal);
        const expiresAt = new Date(Date.now() + 30 * 24 * 3600 * 1000);
        // Store session
        try {
            const existing = await SessionsRepo.findByUserAndDevice(superAdminId, deviceId);
            if (existing)
                await SessionsRepo.revoke(existing.id);
            await SessionsRepo.create({ userId: superAdminId, deviceId, refreshTokenHash, expiresAt });
        }
        catch (e) {
            // Continue even if session storage fails
        }
        const user = { id: superAdminId, email, role: "main_admin", plan: "business" };
        return { user, accessToken, refreshToken: refreshTokenVal };
    },
    async refresh(refreshToken, deviceId) {
        let payload;
        try {
            payload = verifyRefreshToken(refreshToken);
        }
        catch {
            throw new AppError(401, "INVALID_REFRESH", "Invalid refresh token");
        }
        if (payload.deviceId !== deviceId)
            throw new AppError(401, "INVALID_REFRESH", "Invalid device");
        // Rotation: revoke existing, issue new
        const accessToken = issueAccessToken({ id: payload.id, role: payload.role || "CASHIER", plan: payload.plan || "BASIC" });
        const newRefresh = issueRefreshToken({ id: payload.id, deviceId });
        const refreshTokenHash = await hashPassword(newRefresh);
        const existing = await SessionsRepo.findByUserAndDevice(payload.id, deviceId);
        if (existing)
            await SessionsRepo.revoke(existing.id);
        const expiresAt = new Date(Date.now() + 30 * 24 * 3600 * 1000);
        await SessionsRepo.create({ userId: payload.id, deviceId, refreshTokenHash, expiresAt });
        return { accessToken, refreshToken: newRefresh };
    }
};
