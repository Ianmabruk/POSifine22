import { sqlite } from "../../database/sqlite/client";
export const SessionsRepo = {
    async create(session) {
        return sqlite.session.create({ data: { ...session } });
    },
    async findByUserAndDevice(userId, deviceId) {
        return sqlite.session.findFirst({ where: { userId, deviceId, revokedAt: null } });
    },
    async revoke(sessionId) {
        return sqlite.session.update({ where: { id: sessionId }, data: { revokedAt: new Date(), version: { increment: 1 } } });
    }
};
