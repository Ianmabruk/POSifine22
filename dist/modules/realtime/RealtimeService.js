import { initRealtime } from "./gateway";
import { env } from "../../config/env";
import jwt from "jsonwebtoken";
const connectedUsers = new Map();
const realtimeService = {
    io: null,
    connectedUsers,
    init(server) {
        this.io = initRealtime(server);
        this.io.on("connection", (socket) => {
            const token = (socket.handshake.auth?.token || socket.handshake.query?.token);
            if (!token) {
                socket.disconnect(true);
                return;
            }
            try {
                const payload = jwt.verify(token, env.JWT_SECRET);
                const user = {
                    id: payload.id,
                    role: payload.role,
                    plan: payload.plan || "STANDARD"
                };
                connectedUsers.set(socket.id, user);
                socket.join(`user:${user.id}`);
                socket.join(`role:${user.role}`);
                console.log(`User ${user.id} (${user.role}) connected`);
            }
            catch (error) {
                console.error("Socket authentication failed:", error);
                socket.disconnect(true);
            }
        });
    },
    getUser(socketId) {
        return connectedUsers.get(socketId);
    },
    getUserById(userId) {
        for (const [socketId, user] of connectedUsers.entries()) {
            if (user.id === userId) {
                return user;
            }
        }
        return undefined;
    },
    broadcastToRole(role, event, data) {
        if (this.io) {
            this.io.to(`role:${role}`).emit(event, data);
            console.log(`Broadcasting ${event} to role: ${role}`);
        }
    },
    broadcastToUser(userId, event, data) {
        if (this.io) {
            const user = this.getUserById(userId);
            if (user) {
                this.io.to(`user:${userId}`).emit(event, data);
                console.log(`Broadcasting ${event} to user: ${userId}`);
            }
        }
    },
    broadcastToAdmins(event, data) {
        if (this.io) {
            this.io.to("role:main_admin").emit(event, data);
            this.io.to("role:admin").emit(event, data);
            console.log(`Broadcasting ${event} to all admin roles`);
        }
    },
    getConnectionCount() {
        return this.io ? this.io.sockets.size : 0;
    }
};
export default realtimeService;
