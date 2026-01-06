import express from "express";
import { signup, login, pinLogin } from "../controllers/authController.js";

const router = express.Router();

router.post("/signup", signup);
router.post("/login", login);
router.post("/pin-login", pinLogin);

export default router;