import express from "express";
import { getUsers, createUser, verifyToken } from "../controllers/userController.js";

const router = express.Router();

router.get("/", verifyToken, getUsers);
router.post("/", verifyToken, createUser);

export default router;