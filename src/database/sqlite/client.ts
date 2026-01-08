import { PrismaClient as PrismaClientSqlite } from "./generated";
import { logger } from "../../config/logger";

export const sqlite = new PrismaClientSqlite();

async function init() {
  await sqlite.$executeRawUnsafe("PRAGMA journal_mode=WAL;");
  await sqlite.$executeRawUnsafe("PRAGMA synchronous=FULL;");
  await sqlite.$executeRawUnsafe("PRAGMA foreign_keys=ON;");
  logger.info("SQLite pragmas applied (WAL, FULL, FK=ON)");
}

init().catch((e) => {
  logger.error({ err: e }, "SQLite init failed");
});
