import { PrismaClient as PrismaClientMysql } from "./generated";
import { logger } from "../../config/logger";
export const mysql = new PrismaClientMysql();
mysql.$connect().then(() => logger.info("MySQL Prisma connected")).catch((e) => {
    logger.error({ err: e }, "MySQL connect failed");
});
