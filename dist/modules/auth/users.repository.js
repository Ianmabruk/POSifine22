import { sqlite } from "../../database/sqlite/client";
export const UsersRepo = {
    async findByEmail(email) {
        return sqlite.user.findUnique({ where: { email } });
    },
    async create(user) {
        return sqlite.user.create({ data: { email: user.email, passwordHash: user.passwordHash, role: user.role } });
    },
    async updateLogin(id) {
        return sqlite.user.update({ where: { id }, data: { lastLoginAt: new Date(), version: { increment: 1 } } });
    }
};
