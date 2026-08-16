import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { validate } from '../../middlewares/validate';
import { authenticateJWT, authorize, AuthRequest } from '../../middlewares/auth';
import { SubscriptionService } from './subscription.service';
import { PrismaClient } from '@prisma/client';
import { ok } from '../../utils/response';

const prisma = new PrismaClient();
const subscriptionService = new SubscriptionService();

const router = Router();

const createTrialSchema = z.object({
  body: z.object({
    plan: z.enum(['STARTER', 'PROFESSIONAL', 'ENTERPRISE']),
  }),
});

const extendTrialSchema = z.object({
  body: z.object({
    subscriptionId: z.string().uuid(),
    days: z.number().int().positive(),
    reason: z.string().min(1),
  }),
});

const createPaymentSchema = z.object({
  body: z.object({
    subscriptionId: z.string().uuid(),
    amount: z.number().positive(),
    currency: z.string().default('KES'),
    paymentMethod: z.enum(['CASH', 'MPESA', 'CARD', 'BANK_TRANSFER', 'PAYPAL', 'CREDIT']),
    paymentReference: z.string().min(1),
    payerName: z.string().min(1),
    payerEmail: z.string().email(),
    payerPhone: z.string().optional(),
    businessName: z.string().min(1),
    selectedPlan: z.string().min(1),
    notes: z.string().optional(),
  }),
});

const approvePaymentSchema = z.object({
  body: z.object({
    paymentId: z.string().uuid(),
  }),
});

const rejectPaymentSchema = z.object({
  body: z.object({
    paymentId: z.string().uuid(),
    reason: z.string().min(1),
  }),
});

// Public routes
router.get('/plans', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const plans = await subscriptionService.getPlans();
    res.json(ok(plans));
  } catch (e) { next(e); }
});

// Protected routes - require authentication
router.post('/trial', authenticateJWT, validate(createTrialSchema), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const accountId = req.user!.accountId;
    const { plan } = req.body;
    const subscription = await subscriptionService.createTrialSubscription(accountId, plan);
    res.status(201).json(ok(subscription));
  } catch (e) { next(e); }
});

router.get('/subscription', authenticateJWT, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const accountId = req.user!.accountId;
    const subscription = await subscriptionService.getSubscriptionByAccount(accountId);
    res.json(ok(subscription));
  } catch (e) { next(e); }
});

router.post('/payment', authenticateJWT, validate(createPaymentSchema), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const accountId = req.user!.accountId;
    const payment = await subscriptionService.createPendingPayment({ ...req.body, accountId });
    res.status(201).json(ok(payment));
  } catch (e) { next(e); }
});

// Main Admin only routes
router.get('/admin/stats', authenticateJWT, authorize(['MAIN_ADMIN']), async (_req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const stats = await subscriptionService.getSubscriptionStats();
    res.json(ok(stats));
  } catch (e) { next(e); }
});

router.get('/admin/businesses', authenticateJWT, authorize(['MAIN_ADMIN']), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { page = 1, limit = 20, search, status } = req.query;
    const skip = (Number(page) - 1) * Number(limit);
    const take = Number(limit);

    const where: any = {};
    if (search) {
      where.OR = [
        { businessName: { contains: String(search), mode: 'insensitive' } },
        { ownerEmail: { contains: String(search), mode: 'insensitive' } },
      ];
    }
    if (status) where.subscriptionStatus = status;

    const [businesses, total] = await Promise.all([
      prisma.account.findMany({
        where,
        skip,
        take,
        orderBy: { createdAt: 'desc' },
        include: { subscriptions: { include: { plan: true } } },
      }),
      prisma.account.count({ where }),
    ]);

    res.json(ok({ businesses, total, page: Number(page), limit: Number(limit) }));
  } catch (e) { next(e); }
});

router.get('/admin/trials/active', authenticateJWT, authorize(['MAIN_ADMIN']), async (_req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const trials = await prisma.trial.findMany({
      where: { status: 'ACTIVE' },
      include: { account: { select: { id: true, businessName: true, ownerEmail: true, plan: true } } },
      orderBy: { endsAt: 'asc' },
    });
    res.json(ok(trials));
  } catch (e) { next(e); }
});

router.get('/admin/trials/expired', authenticateJWT, authorize(['MAIN_ADMIN']), async (_req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const trials = await prisma.trial.findMany({
      where: { status: 'EXPIRED' },
      include: { account: { select: { id: true, businessName: true, ownerEmail: true, plan: true } } },
      orderBy: { endsAt: 'desc' },
    });
    res.json(ok(trials));
  } catch (e) { next(e); }
});

router.post('/admin/trials/extend', authenticateJWT, authorize(['MAIN_ADMIN']), validate(extendTrialSchema), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { subscriptionId, days, reason } = req.body;
    const result = await subscriptionService.extendTrial(subscriptionId, days, req.user!.id, reason);
    res.json(ok(result));
  } catch (e) { next(e); }
});

router.get('/admin/subscriptions', authenticateJWT, authorize(['MAIN_ADMIN']), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { page = 1, limit = 20, status } = req.query;
    const skip = (Number(page) - 1) * Number(limit);
    const take = Number(limit);

    const where: any = {};
    if (status) where.status = status;

    const [subscriptions, total] = await Promise.all([
      prisma.subscription.findMany({
        where,
        skip,
        take,
        orderBy: { createdAt: 'desc' },
        include: { account: { select: { id: true, businessName: true, ownerEmail: true } }, plan: true },
      }),
      prisma.subscription.count({ where }),
    ]);

    res.json(ok({ subscriptions, total, page: Number(page), limit: Number(limit) }));
  } catch (e) { next(e); }
});

router.get('/admin/payments', authenticateJWT, authorize(['MAIN_ADMIN']), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { page = 1, limit = 20, status } = req.query;
    const skip = (Number(page) - 1) * Number(limit);
    const take = Number(limit);

    const where: any = {};
    if (status) where.paymentStatus = status;

    const [payments, total] = await Promise.all([
      prisma.payment.findMany({
        where,
        skip,
        take,
        orderBy: { createdAt: 'desc' },
        include: { account: { select: { id: true, businessName: true, ownerEmail: true } }, subscription: true },
      }),
      prisma.payment.count({ where }),
    ]);

    res.json(ok({ payments, total, page: Number(page), limit: Number(limit) }));
  } catch (e) { next(e); }
});

router.post('/admin/payments/approve', authenticateJWT, authorize(['MAIN_ADMIN']), validate(approvePaymentSchema), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { paymentId } = req.body;
    const result = await subscriptionService.approvePayment(paymentId, req.user!.id);
    res.json(ok(result));
  } catch (e) { next(e); }
});

router.post('/admin/payments/reject', authenticateJWT, authorize(['MAIN_ADMIN']), validate(rejectPaymentSchema), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { paymentId, reason } = req.body;
    const result = await subscriptionService.rejectPayment(paymentId, req.user!.id, reason);
    res.json(ok(result));
  } catch (e) { next(e); }
});

router.post('/admin/subscriptions/:id/suspend', authenticateJWT, authorize(['MAIN_ADMIN']), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const result = await subscriptionService.suspendSubscription(req.params.id);
    res.json(ok(result));
  } catch (e) { next(e); }
});

router.post('/admin/subscriptions/:id/reactivate', authenticateJWT, authorize(['MAIN_ADMIN']), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const result = await subscriptionService.reactivateSubscription(req.params.id);
    res.json(ok(result));
  } catch (e) { next(e); }
});

router.get('/admin/revenue', authenticateJWT, authorize(['MAIN_ADMIN']), async (_req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { days = 30 } = _req.query;
    const since = new Date(Date.now() - Number(days) * 24 * 60 * 60 * 1000);

    const dailyRevenue = await prisma.payment.groupBy({
      by: ['createdAt'],
      where: { paymentStatus: 'COMPLETED', createdAt: { gte: since } },
      _sum: { amount: true },
      orderBy: { createdAt: 'asc' },
    });

    const packageBreakdown = await prisma.payment.groupBy({
      by: ['selectedPlan'],
      where: { paymentStatus: 'COMPLETED' },
      _count: { selectedPlan: true },
      _sum: { amount: true },
    });

    res.json(ok({ dailyRevenue, packageBreakdown }));
  } catch (e) { next(e); }
});

router.get('/admin/audit-logs', authenticateJWT, authorize(['MAIN_ADMIN']), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { page = 1, limit = 50, type, accountId } = req.query;
    const skip = (Number(page) - 1) * Number(limit);
    const take = Number(limit);

    const where: any = {};
    if (type) where.type = type;
    if (accountId) where.accountId = accountId;

    const [logs, total] = await Promise.all([
      prisma.auditLog.findMany({
        where,
        skip,
        take,
        orderBy: { createdAt: 'desc' },
        include: { account: { select: { businessName: true } }, user: { select: { email: true, name: true } } },
      }),
      prisma.auditLog.count({ where }),
    ]);

    res.json(ok({ logs, total, page: Number(page), limit: Number(limit) }));
  } catch (e) { next(e); }
});

export default router;