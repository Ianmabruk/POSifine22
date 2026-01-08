import { sqlite } from "../../database/sqlite/client";
export const SyncQueueRepo = {
    nextBatch: (limit) => sqlite.syncQueue.findMany({ orderBy: [{ createdAt: "asc" }], take: limit }),
    markAttempt: (id, error) => sqlite.syncQueue.update({ where: { id }, data: { attemptCount: { increment: 1 }, lastAttemptAt: new Date(), error } }),
    delete: (id) => sqlite.syncQueue.delete({ where: { id } })
};
