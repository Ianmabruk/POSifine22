import express from "express";
import http from "http";
import { Server } from "socket.io";
import cors from "cors";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const server = http.createServer(app);

export const io = new Server(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST", "PUT", "DELETE"]
  }
});

app.use(cors());
app.use(express.json());

io.on("connection", socket => {
  console.log("Socket connected:", socket.id);

  socket.on("joinAccount", accountId => {
    socket.join(accountId);
    console.log(`Joined account room: ${accountId}`);
  });

  socket.on("disconnect", () => {
    console.log("Socket disconnected");
  });
});

export default server;
