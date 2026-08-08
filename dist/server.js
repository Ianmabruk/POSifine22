import express from "express";
import helmet from "helmet";
import cors from "cors";
import http from "http";
import { env } from "./config/env";
import { logger } from "./config/logger";
import { errorHandler } from "./middlewares/errorHandler";
import authRoutes from "./modules/auth/auth.routes";
import productsRoutes from "./modules/products/products.routes";
import superAdminRoutes from "./modules/super-admin/super-admin.routes";
import subscriptionRoutes from "./modules/main-admin/main-admin.routes";
import { startSyncWorker } from "./modules/sync/sync.worker";
import { initRealtime } from "./modules/realtime/gateway";
import { trialEnforcementMiddleware } from "./middlewares/trialEnforcement";
import { startTrialExpiryJob, startTrialNotificationJob } from "./modules/trial/trial.jobs";
import { PrismaClient } from '@prisma/client';
const prisma = new PrismaClient();
const app = express();
app.use(helmet());
app.use(cors({ origin: env.CORS_ORIGIN === "*" ? true : env.CORS_ORIGIN, credentials: true }));
app.use(express.json());
app.get("/api/v1/health", async (_req, res) => {
    res.json({ success: true, data: { status: "ok", time: new Date().toISOString() } });
});
// Public auth routes (no trial enforcement)
app.use("/api/v1/auth", authRoutes);
// Apply trial enforcement middleware to all other API routes
app.use("/api/v1", trialEnforcementMiddleware);
// Protected routes
app.use("/api/v1/products", productsRoutes);
app.use("/api/v1/subscription", subscriptionRoutes);
app.use("/api/v1/super-admin", superAdminRoutes);
app.use("/api/v1/main-admin", subscriptionRoutes);
app.use(errorHandler);
const server = http.createServer(app);
initRealtime(server);
startSyncWorker();
// Start trial expiry background jobs
startTrialExpiryJob(24 * 60 * 60 * 1000); // Check daily
startTrialNotificationJob();
server.listen(env.PORT, () => {
    logger.info(`POS backend listening on port ${env.PORT}`);
});
