import express from "express";
import helmet from "helmet";
import cors from "cors";
import http from "http";
import { env } from "./config/env";
import { logger } from "./config/logger";
import { errorHandler } from "./middlewares/errorHandler";
import authRoutes from "./modules/auth/auth.routes";
import productsRoutes from "./modules/products/products.routes";
import { startSyncWorker } from "./modules/sync/sync.worker";
import { initRealtime } from "./modules/realtime/gateway";

const app = express();
app.use(helmet());
app.use(cors({ origin: env.CORS_ORIGIN === "*" ? true : env.CORS_ORIGIN, credentials: true }));
app.use(express.json());

app.get("/api/v1/health", async (_req, res) => {
  // Basic health: local only. MySQL may be down and that is surfaced in logs.
  res.json({ success: true, data: { status: "ok", time: new Date().toISOString() } });
});

app.use("/api/v1/auth", authRoutes);
app.use("/api/v1/products", productsRoutes);

app.use(errorHandler);

const server = http.createServer(app);
initRealtime(server);
startSyncWorker();

server.listen(env.PORT, () => {
  logger.info(`POS backend listening on port ${env.PORT}`);
});
