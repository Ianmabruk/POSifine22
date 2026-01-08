import { env } from "../../config/env";
import { logger } from "../../config/logger";
import { SyncService } from "./sync.service";
let timer = null;
export function startSyncWorker() {
    if (timer)
        return;
    logger.info("Starting sync worker");
    timer = setInterval(async () => {
        try {
            await SyncService.pushBatch(env.SYNC_MAX_BATCH);
        }
        catch (e) {
            logger.warn({ e }, "Sync worker iteration error");
        }
    }, env.SYNC_WORKER_INTERVAL_MS);
}
export function stopSyncWorker() { if (timer)
    clearInterval(timer); timer = null; }
