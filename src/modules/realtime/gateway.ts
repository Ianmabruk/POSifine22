import { Server } from "socket.io";
import { env } from "../../config/env";
import jwt from "jsonwebtoken";

export function initRealtime(httpServer: any) {
  const io = new Server(httpServer, { path: env.SOCKET_IO_PATH, cors: { origin: "*" } });

  io.use((socket, next) => {
    const token = (socket.handshake.auth?.token || socket.handshake.query?.token) as string | undefined;
    if (!token) return next(new Error("UNAUTHORIZED"));
    try {
      const payload = jwt.verify(token, env.JWT_SECRET) as any;
      (socket as any).user = { id: payload.id, role: payload.role, plan: payload.plan };
      if (payload.plan !== "ULTRA") return next(new Error("PLAN_REQUIRED"));
      return next();
    } catch {
      return next(new Error("UNAUTHORIZED"));
    }
  });

  io.on("connection", (socket) => {
    const u = (socket as any).user;
    socket.join(`user:${u.id}`);
    socket.join(`role:${u.role}`);
  });

  return io;
}
