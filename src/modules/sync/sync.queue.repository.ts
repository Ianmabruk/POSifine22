import { sqlite } from "../../database/sqlite/client";

export const SyncQueueRepo = {
  nextBatch: (limit: number) => sqlite.syncQueue.findMany({ orderBy: [{ createdAt: "asc" }], take: limit }),
  markAttempt: (id: string, error?: string) => sqlite.syncQueue.update({ where: { id }, data: { attemptCount: { increment: 1 }, lastAttemptAt: new Date(), error } }),
  delete: (id: string) => sqlite.syncQueue.delete({ where: { id } })
};
