import { PrismaClient } from "@prisma/client";
const prisma = new PrismaClient();
export const UsersRepo = {
    async findByEmail(email) {
        return prisma.user.findUnique({ where: { email } });
    },
    async create(user) {
        return prisma.user.create({ data: { email: user.email, passwordHash: user.passwordHash, role: user.role, deviceMode: user.deviceMode } });
    },
    async updateLogin(id) {
        return prisma.user.update({ where: { id }, data: { lastLoginAt: new Date(), version: { increment: 1 } } });
    },
    async updateDeviceMode(id, deviceMode) {
        return prisma.user.update({ where: { id }, data: { deviceMode } });
    }
};
