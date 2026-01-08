import { sqlite } from "../../database/sqlite/client";

export const UsersRepo = {
  async findByEmail(email: string) {
    return sqlite.user.findUnique({ where: { email } });
  },
  async create(user: { email: string; passwordHash: string; role: "ADMIN" | "CASHIER" }) {
    return sqlite.user.create({ data: { email: user.email, passwordHash: user.passwordHash, role: user.role } });
  },
  async updateLogin(id: string) {
    return sqlite.user.update({ where: { id }, data: { lastLoginAt: new Date(), version: { increment: 1 } } });
  }
};
