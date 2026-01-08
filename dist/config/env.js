import { z } from "zod";
import dotenv from "dotenv";
dotenv.config();
const envSchema = z.object({
    NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
    PORT: z.coerce.number().default(8080),
    JWT_SECRET: z.string().min(24),
    JWT_EXPIRES_IN: z.string().default("15m"),
    REFRESH_TOKEN_SECRET: z.string().min(24),
    REFRESH_TOKEN_EXPIRES_IN: z.string().default("30d"),
    SQLITE_URL: z.string().default("file:./data/pos.sqlite"),
    MYSQL_URL: z.string(),
    SYNC_WORKER_INTERVAL_MS: z.coerce.number().default(5000),
    SYNC_MAX_BATCH: z.coerce.number().default(100),
    SYNC_MAX_ATTEMPTS: z.coerce.number().default(8),
    BCRYPT_ROUNDS: z.coerce.number().default(12),
    CORS_ORIGIN: z.string().default("*"),
    SOCKET_IO_PATH: z.string().default("/socket.io")
});
export const env = envSchema.parse(process.env);
