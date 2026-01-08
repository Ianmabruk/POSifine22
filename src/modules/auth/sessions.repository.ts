import { sqlite } from "../../database/sqlite/client";

export const SessionsRepo = {
  async create(session: { userId: string; deviceId: string; refreshTokenHash: string; ip?: string; userAgent?: string; expiresAt: Date }) {
    return sqlite.session.create({ data: { ...session } });
  },
  async findByUserAndDevice(userId: string, deviceId: string) {
    return sqlite.session.findFirst({ where: { userId, deviceId, revokedAt: null } });
  },
  async revoke(sessionId: string) {
    return sqlite.session.update({ where: { id: sessionId }, data: { revokedAt: new Date(), version: { increment: 1 } } });
  }
};
