import { Router } from "express";
import { AuthController } from "./auth.controller";
import { validate } from "../../middlewares/validate";
import { signupSchema, loginSchema, refreshSchema } from "./auth.schemas";
import { authenticateJWT } from "../../middlewares/auth";

const router = Router();

// Public authentication endpoints
router.post("/signup", validate(signupSchema), AuthController.signup);
router.post("/login", validate(loginSchema), AuthController.login);
router.post("/refresh", validate(refreshSchema), AuthController.refresh);

// Protected user endpoint
router.get("/me", authenticateJWT, AuthController.me);

export default router;