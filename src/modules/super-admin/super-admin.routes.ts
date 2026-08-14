import { Router } from "express";
import { AuthController } from "../auth/auth.controller";
import { validate } from "../../middlewares/validate";
import { loginSchema } from "../auth/auth.schemas";
import { authenticateJWT, authorize } from "../../middlewares/auth";

const router = Router();

// Super Admin Auth
router.post("/auth/login", validate(loginSchema), AuthController.superAdminLogin);

// Protected Super Admin endpoints - using mock data since Prisma is mocked
router.get("/stats", authenticateJWT, authorize(["main_admin"]), async (_req, res) => {
  // Mock stats data
  res.json({ 
    success: true, 
    data: { 
      total_users: 1245, 
      active_businesses: 892, 
      expired_trials: 312, 
      paid_subscribers: 587 
    } 
  });
});

router.get("/businesses", authenticateJWT, authorize(["main_admin"]), async (_req, res) => {
  // Mock businesses data
  res.json({ 
    success: true, 
    businesses: [
      { id: 1, business_name: 'Fresh Mart', owner_email: 'admin@freshmart.co.ke', plan: 'business', is_active: true, created_at: '2024-01-15', user_count: 5 },
      { id: 2, business_name: 'Tech Store', owner_email: 'info@techstore.co.ke', plan: 'custom', is_active: true, created_at: '2024-02-20', user_count: 12 },
      { id: 3, business_name: 'Cafe Corner', owner_email: 'owner@cafecorner.co.ke', plan: 'starter', is_active: false, created_at: '2024-03-10', user_count: 2 },
    ] 
  });
});

router.get("/users", authenticateJWT, authorize(["main_admin"]), async (_req, res) => {
  // Mock users data
  res.json({ 
    success: true, 
    users: [
      { id: 1, email: 'admin@freshmart.co.ke', role: 'admin', plan: 'business', created_at: '2024-01-15' },
      { id: 2, email: 'info@techstore.co.ke', role: 'admin', plan: 'custom', created_at: '2024-02-20' },
    ] 
  });
});

router.get("/health", authenticateJWT, authorize(["main_admin"]), async (_req, res) => {
  res.json({ success: true, data: { database: "connected", api: "operational", ws: "connected" } });
});

router.get("/logs", authenticateJWT, authorize(["main_admin"]), async (_req, res) => {
  // Mock audit logs
  res.json({ 
    success: true, 
    logs: [
      { id: 1, action: 'LOGIN', user: 'admin@freshmart.co.ke', timestamp: new Date().toISOString() },
      { id: 2, action: 'SALE', user: 'admin@freshmart.co.ke', timestamp: new Date().toISOString() },
    ] 
  });
});

export default router;