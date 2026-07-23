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
  DATABASE_URL: z.string(),
  SYNC_WORKER_INTERVAL_MS: z.coerce.number().default(5000),
  SYNC_MAX_BATCH: z.coerce.number().default(100),
  SYNC_MAX_ATTEMPTS: z.coerce.number().default(8),
  BCRYPT_ROUNDS: z.coerce.number().default(12),
  CORS_ORIGIN: z.string().default("*"),
  SOCKET_IO_PATH: z.string().default("/socket.io"),
  EMERGENCY_RECOVERY_KEY: z.string().optional(),
  
  // Email
  SENDGRID_API_KEY: z.string().optional(),
  FROM_EMAIL: z.string().email().optional(),
  FROM_NAME: z.string().optional(),
  REPLY_TO: z.string().email().optional(),
  ADMIN_EMAIL: z.string().email().optional(),
  APP_LOGIN_URL: z.string().url().optional(),
  FRONTEND_URL: z.string().url().optional(),
  
  // AI
  GEMINI_API_KEY: z.string().optional(),
  
  // Storage
  CLOUDINARY_CLOUD_NAME: z.string().optional(),
  CLOUDINARY_API_KEY: z.string().optional(),
  CLOUDINARY_API_SECRET: z.string().optional(),
  SUPABASE_URL: z.string().url().optional(),
  SUPABASE_ANON_KEY: z.string().optional(),
  SUPABASE_SERVICE_ROLE_KEY: z.string().optional(),
});

export const env = envSchema.parse(process.env);