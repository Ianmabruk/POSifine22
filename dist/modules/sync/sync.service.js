import { SyncQueueRepo } from "./sync.queue.repository";
import { mysql } from "../../database/mysql/client";
import { sqlite } from "../../database/sqlite/client";
import { logger } from "../../config/logger";
export const SyncService = {
    async pushBatch(limit) {
        const items = await SyncQueueRepo.nextBatch(limit);
        for (const it of items) {
            try {
                if (it.entityType === "Product") {
                    const p = await sqlite.product.findUnique({ where: { id: it.entityId } });
                    if (!p) {
                        await SyncQueueRepo.delete(it.id);
                        continue;
                    }
                    // Upsert to MySQL deterministically by id
                    await mysql.$transaction(async (tx) => {
                        const existing = await tx.product.findUnique({ where: { id: p.id } });
                        if (!existing) {
                            await tx.product.create({ data: { ...p } });
                        }
                        else if (existing.version < p.version || existing.updatedAt < p.updatedAt) {
                            await tx.product.update({ where: { id: p.id }, data: { ...p } });
                        } // else idempotent no-op
                    });
                    await sqlite.product.update({ where: { id: p.id }, data: { syncStatus: "SYNCED" } });
                }
                await SyncQueueRepo.delete(it.id);
            }
            catch (e) {
                logger.warn({ id: it.id, err: e?.message }, "Sync push failed; will retry");
                await SyncQueueRepo.markAttempt(it.id, e?.message || String(e));
            }
        }
    }
};
