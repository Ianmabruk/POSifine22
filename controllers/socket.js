import { Server } from "socket.io";

let io;

export const initSocket = (server) => {
  io = new Server(server, {
    cors: {
      origin: "*",
      methods: ["GET", "POST", "PUT", "DELETE"]
    }
  });

  io.on("connection", (socket) => {
    socket.on("joinAccount", (accountId) => {
      socket.join(accountId);
    });
  });

  console.log("Socket.IO initialized");
};

export const getIO = () => {
  if (!io) throw new Error("Socket.io not initialized");
  return io;
};
