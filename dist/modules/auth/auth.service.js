import { UsersRepo } from "./users.repository";
import { SessionsRepo } from "./sessions.repository";
import { hashPassword, comparePassword } from "./password";
import { issueAccessToken, issueRefreshToken, verifyRefreshToken } from "./tokens";
import { AppError } from "../../utils/errors";
import { PrismaClient } from "@prisma/client";
const prisma = new PrismaClient();
export const AuthService = {
    async signup(email, password, role, deviceId, deviceMode) {
        const existing = await UsersRepo.findByEmail(email);
        if (existing)
            throw new AppError(409, "EMAIL_TAKEN", "Email already registered");
        const passwordHash = await hashPassword(password);
        const user = await UsersRepo.create({ email, passwordHash, role, deviceMode });
        const accessToken = issueAccessToken({ id: user.id, role: user.role, plan: "BASIC", deviceMode: user.deviceMode });
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
        const accessToken = issueAccessToken({ id: user.id, role: user.role, plan: "BASIC", deviceMode: user.deviceMode });
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
        const superAdminId = "main_admin_" + Date.now();
        const accessToken = issueAccessToken({ id: superAdminId, role: "main_admin", plan: "business" });
        const refreshTokenVal = issueRefreshToken({ id: superAdminId, deviceId });
        const refreshTokenHash = await hashPassword(refreshTokenVal);
        const expiresAt = new Date(Date.now() + 30 * 24 * 3600 * 1000);
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
        const dbUser = await prisma.user.findUnique({ where: { id: payload.id } });
        if (!dbUser)
            throw new AppError(401, "INVALID_REFRESH", "User not found");
        const accessToken = issueAccessToken({ id: payload.id, role: payload.role || "CASHIER", plan: payload.plan || "BASIC", deviceMode: dbUser.deviceMode });
        const newRefresh = issueRefreshToken({ id: payload.id, deviceId });
        const refreshTokenHash = await hashPassword(newRefresh);
        const existing = await SessionsRepo.findByUserAndDevice(payload.id, deviceId);
        if (existing)
            await SessionsRepo.revoke(existing.id);
        const expiresAt = new Date(Date.now() + 30 * 24 * 3600 * 1000);
        await SessionsRepo.create({ userId: payload.id, deviceId, refreshTokenHash, expiresAt });
        return { accessToken, refreshToken: newRefresh };
    },
    async me(userId) {
        const user = await prisma.user.findUnique({
            where: { id: userId },
            select: {
                id: true,
                email: true,
                name: true,
                role: true,
                deviceMode: true,
                accountId: true,
                businessType: true,
                businessRole: true,
                isActive: true,
                permissions: true,
            }
        });
        if (!user)
            throw new AppError(404, "USER_NOT_FOUND", "User not found");
        return user;
    }
};
