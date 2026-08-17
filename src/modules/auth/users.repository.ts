import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

export const UsersRepo = {
  async findByEmail(email: string) {
    return prisma.user.findUnique({ where: { email } });
  },
  async create(user: { email: string; passwordHash: string; role: "ADMIN" | "CASHIER"; deviceMode?: string }) {
    return prisma.user.create({ data: { email: user.email, passwordHash: user.passwordHash, role: user.role, deviceMode: user.deviceMode, name: user.email, accountId: "pending" } as any });
  },
  async updateLogin(id: string) {
    return prisma.user.update({ where: { id }, data: { lastLoginAt: new Date(), version: { increment: 1 } } });
  },
  async updateDeviceMode(id: string, deviceMode: string) {
    return prisma.user.update({ where: { id }, data: { deviceMode } as any });
  }
};
