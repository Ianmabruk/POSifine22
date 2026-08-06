import { Server as SocketIOServer } from "socket.io";
import { initRealtime } from "./gateway";
import { env } from "../../config/env";
import jwt from "jsonwebtoken";

const connectedUsers = new Map<string, any>();

const realtimeService = {
  io: null,
  connectedUsers,
  init(server: any) {
    this.io = initRealtime(server);
    
    this.io.on("connection", (socket) => {
      const token = (socket.handshake.auth?.token || socket.handshake.query?.token) as string | undefined;
      if (!token) {
        socket.disconnect(true);
        return;
      }

      try {
        const payload = jwt.verify(token, env.JWT_SECRET) as any;
        const user = {
          id: payload.id,
          role: payload.role,
          plan: payload.plan || "STANDARD"
        };
        
        connectedUsers.set(socket.id, user);
        socket.join(`user:${user.id}`);
        socket.join(`role:${user.role}`);
        console.log(`User ${user.id} (${user.role}) connected`);
      } catch (error) {
        console.error("Socket authentication failed:", error);
        socket.disconnect(true);
      }
    });
  },
  getUser(socketId: string) {
    return connectedUsers.get(socketId);
  },
  getUserById(userId: string) {
    for (const [socketId, user] of connectedUsers.entries()) {
      if (user.id === userId) {
        return user;
      }
    }
    return undefined;
  },
  broadcastToRole(role: string, event: string, data: any) {
    if (this.io) {
      this.io.to(`role:${role}`).emit(event, data);
      console.log(`Broadcasting ${event} to role: ${role}`);
    }
  },
  broadcastToUser(userId: string, event: string, data: any) {
    if (this.io) {
      const user = this.getUserById(userId);
      if (user) {
        this.io.to(`user:${userId}`).emit(event, data);
        console.log(`Broadcasting ${event} to user: ${userId}`);
      }
    }
  },
  broadcastToAdmins(event: string, data: any) {
    if (this.io) {
      this.io.to("role:main_admin").emit(event, data);
      this.io.to("role:admin").emit(event, data);
      console.log(`Broadcasting ${event} to all admin roles`);
    }
  },
  getConnectionCount(): number {
    return this.io ? this.io.sockets.size : 0;
  }
};

export default realtimeService;
