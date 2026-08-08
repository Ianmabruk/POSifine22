import { Router } from 'express';
import { PrismaClient } from '@prisma/client';
import { authenticateJWT, authorize } from '../../middlewares/auth';
import { validate } from '../../middlewares/validate';
import { z } from 'zod';
import { ok } from '../../utils/response';
import { AppError } from '../../utils/errors';
import bcrypt from 'bcrypt';
import crypto from 'crypto';
const router = Router();
const prisma = new PrismaClient();
// Validation schemas
const approvePaymentSchema = z.object({
    body: z.object({
        paymentId: z.string().uuid(),
        action: z.enum(['approve', 'reject']),
        rejectionReason: z.string().optional(),
    }),
});
const extendTrialSchema = z.object({
    body: z.object({
        accountId: z.string().uuid(),
        days: z.number().int().min(1).max(365),
        reason: z.string().min(1).max(500),
    }),
});
const suspendAccountSchema = z.object({
    body: z.object({
        accountId: z.string().uuid(),
        reason: z.string().min(1).max(500).optional(),
    }),
});
const reactivateAccountSchema = z.object({
    body: z.object({
        accountId: z.string().uuid(),
    }),
});
const resetPasswordSchema = z.object({
    body: z.object({
        email: z.string().email(),
        newPassword: z.string().min(8),
        token: z.string().min(10),
    }),
});
const createMainAdminSchema = z.object({
    body: z.object({
        email: z.string().email(),
        password: z.string().min(8),
        name: z.string().min(1).max(100),
    }),
});
// ============================================================
// DASHBOARD STATISTICS
// ============================================================
router.get('/stats', authenticateJWT, authorize(['MAIN_ADMIN']), async (_req, res, next) => {
    try {
        const [totalBusinesses, activeSubscriptions, expiredTrials, pendingPayments, totalRevenue, monthlyGrowth, totalUsers, activeUsers,] = await Promise.all([
            prisma.account.count(),
            prisma.subscription.count({ where: { status: 'ACTIVE_SUBSCRIPTION' } }),
            prisma.trial.count({ where: { status: 'EXPIRED' } }),
            prisma.payment.count({ where: { paymentStatus: 'PENDING' } }),
            prisma.payment.aggregate({
                where: { paymentStatus: 'COMPLETED' },
                _sum: { amount: true },
            }),
            prisma.account.groupBy({
                by: ['createdAt'],
                where: {
                    createdAt: { gte: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000) },
                },
                _count: true,
            }),
            prisma.user.count(),
            prisma.user.count({ where: { status: 'ACTIVE', lastLoginAt: { gte: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000) } } }),
        ]);
        res.json(ok({
            totalBusinesses,
            activeSubscriptions,
            expiredTrials,
            pendingApprovals: pendingPayments,
            totalRevenue: totalRevenue._sum.amount || 0,
            monthlyGrowth: monthlyGrowth.length,
            totalUsers,
            activeUsers,
        }));
    }
    catch (e) {
        next(e);
    }
});
// ============================================================
// BUSINESS MANAGEMENT
// ============================================================
router.get('/businesses', authenticateJWT, authorize(['MAIN_ADMIN']), async (req, res, next) => {
    try {
        const { page = 1, limit = 20, search, status, plan } = req.query;
        const skip = (Number(page) - 1) * Number(limit);
        const take = Number(limit);
        const where = {};
        if (search) {
            where.OR = [
                { businessName: { contains: String(search), mode: 'insensitive' } },
                { ownerEmail: { contains: String(search), mode: 'insensitive' } },
            ];
        }
        if (status)
            where.status = status;
        if (plan)
            where.plan = plan;
        const [businesses, total] = await Promise.all([
            prisma.account.findMany({
                where,
                skip,
                take,
                orderBy: { createdAt: 'desc' },
                include: {
                    users: { select: { id: true, email: true, role: true, status: true } },
                    subscriptions: { include: { plan: true } },
                    trial: true,
                },
            }),
            prisma.account.count({ where }),
        ]);
        res.json(ok({
            businesses: businesses.map(b => ({
                id: b.id,
                businessName: b.businessName,
                ownerEmail: b.ownerEmail,
                plan: b.plan,
                subscriptionStatus: b.subscriptionStatus,
                status: b.status,
                isLocked: b.isLocked,
                trialEndsAt: b.trialEndsAt,
                subscriptionEndsAt: b.subscriptionEndsAt,
                userCount: b.users.length,
                createdAt: b.createdAt,
            })),
            pagination: { page: Number(page), limit: Number(limit), total, totalPages: Math.ceil(total / take) },
        }));
    }
    catch (e) {
        next(e);
    }
});
router.get('/businesses/:id', authenticateJWT, authorize(['MAIN_ADMIN']), async (req, res, next) => {
    try {
        const business = await prisma.account.findUnique({
            where: { id: req.params.id },
            include: {
                users: { select: { id: true, email: true, name: true, role: true, status: true, lastLoginAt: true, createdAt: true } },
                subscriptions: { include: { plan: true, payments: { orderBy: { createdAt: 'desc' } } } },
                trial: true,
                products: { select: { id: true, name: true, quantity: true, sellingPrice: true, status: true } },
                _count: { select: { sales: true, users: true, products: true } },
            },
        });
        if (!business)
            throw new AppError(404, 'BUSINESS_NOT_FOUND', 'Business not found');
        res.json(ok({ business }));
    }
    catch (e) {
        next(e);
    }
});
router.post('/businesses/:id/suspend', authenticateJWT, authorize(['MAIN_ADMIN']), validate(suspendAccountSchema), async (req, res, next) => {
    try {
        const { accountId, reason } = req.body;
        await prisma.$transaction(async (tx) => {
            await tx.account.update({
                where: { id: accountId },
                data: { isLocked: true, status: 'SUSPENDED' },
            });
            await tx.auditLog.create({
                data: {
                    accountId,
                    type: 'ACCOUNT_LOCKED',
                    entityType: 'Account',
                    entityId: accountId,
                    metadata: { reason, suspendedBy: req.user.id },
                },
            });
        });
        res.json(ok({ success: true, message: 'Business suspended successfully' }));
    }
    catch (e) {
        next(e);
    }
});
router.post('/businesses/:id/activate', authenticateJWT, authorize(['MAIN_ADMIN']), validate(reactivateAccountSchema), async (req, res, next) => {
    try {
        const { accountId } = req.body;
        await prisma.$transaction(async (tx) => {
            await tx.account.update({
                where: { id: accountId },
                data: { isLocked: false, status: 'ACTIVE' },
            });
            await tx.auditLog.create({
                data: {
                    accountId,
                    type: 'ACCOUNT_UNLOCKED',
                    entityType: 'Account',
                    entityId: accountId,
                    metadata: { reactivatedBy: req.user.id },
                },
            });
        });
        res.json(ok({ success: true, message: 'Business reactivated successfully' }));
    }
    catch (e) {
        next(e);
    }
});
// ============================================================
// TRIAL MANAGEMENT
// ============================================================
router.get('/trials', authenticateJWT, authorize(['MAIN_ADMIN']), async (req, res, next) => {
    try {
        const { status, page = 1, limit = 20 } = req.query;
        const skip = (Number(page) - 1) * Number(limit);
        const take = Number(limit);
        const where = {};
        if (status)
            where.status = status;
        const [trials, total] = await Promise.all([
            prisma.trial.findMany({
                where,
                skip,
                take,
                orderBy: { endsAt: 'asc' },
                include: { account: { select: { id: true, businessName: true, ownerEmail: true, plan: true } } },
            }),
            prisma.trial.count({ where }),
        ]);
        res.json(ok({
            trials: trials.map(t => ({
                id: t.id,
                businessName: t.account.businessName,
                ownerEmail: t.account.ownerEmail,
                plan: t.plan,
                status: t.status,
                startedAt: t.startedAt,
                endsAt: t.endsAt,
                extendedAt: t.extendedAt,
                extendedBy: t.extendedBy,
                extensionReason: t.extensionReason,
                daysRemaining: Math.ceil((t.endsAt.getTime() - Date.now()) / (1000 * 60 * 60 * 24)),
            })),
            pagination: { page: Number(page), limit: Number(limit), total, totalPages: Math.ceil(total / take) },
        }));
    }
    catch (e) {
        next(e);
    }
});
router.post('/trials/extend', authenticateJWT, authorize(['MAIN_ADMIN']), validate(extendTrialSchema), async (req, res, next) => {
    try {
        const { accountId, days, reason } = req.body;
        const adminId = req.user.id;
        const trial = await prisma.trial.findUnique({ where: { accountId }, include: { account: true } });
        if (!trial)
            throw new AppError(404, 'TRIAL_NOT_FOUND', 'Trial not found for this account');
        const newEndsAt = new Date(trial.endsAt.getTime() + days * 24 * 60 * 60 * 1000);
        await prisma.$transaction(async (tx) => {
            await tx.trial.update({
                where: { id: trial.id },
                data: {
                    status: 'EXTENDED',
                    endsAt: newEndsAt,
                    extendedAt: new Date(),
                    extendedBy: adminId,
                    extensionReason: reason,
                },
            });
            await tx.account.update({
                where: { id: accountId },
                data: {
                    trialEndsAt: newEndsAt,
                    trialExtendedAt: new Date(),
                    trialExtendedBy: adminId,
                    trialExtensionReason: reason,
                    trialStatus: 'EXTENDED',
                },
            });
            const subscription = await tx.subscription.findFirst({ where: { accountId, status: 'ACTIVE_TRIAL' } });
            if (subscription) {
                await tx.subscription.update({
                    where: { id: subscription.id },
                    data: { trialEndsAt: newEndsAt },
                });
            }
            await tx.auditLog.create({
                data: {
                    accountId,
                    type: 'TRIAL_EXTENDED',
                    entityType: 'Trial',
                    entityId: trial.id,
                    metadata: { extendedBy: adminId, reason, days, newEndDate: newEndsAt.toISOString() },
                },
            });
        });
        res.json(ok({ success: true, newTrialEndsAt: newEndsAt }));
    }
    catch (e) {
        next(e);
    }
});
// ============================================================
// SUBSCRIPTION MANAGEMENT
// ============================================================
router.get('/subscriptions', authenticateJWT, authorize(['MAIN_ADMIN']), async (req, res, next) => {
    try {
        const { status, page = 1, limit = 20 } = req.query;
        const skip = (Number(page) - 1) * Number(limit);
        const take = Number(limit);
        const where = {};
        if (status)
            where.status = status;
        const [subscriptions, total] = await Promise.all([
            prisma.subscription.findMany({
                where,
                skip,
                take,
                orderBy: { createdAt: 'desc' },
                include: { account: { select: { businessName: true, ownerEmail: true } }, plan: true, payments: { orderBy: { createdAt: 'desc' } } },
            }),
            prisma.subscription.count({ where }),
        ]);
        res.json(ok({
            subscriptions: subscriptions.map(s => ({
                id: s.id,
                businessName: s.account.businessName,
                ownerEmail: s.account.ownerEmail,
                plan: s.plan.name,
                status: s.status,
                amount: s.amount,
                currency: s.currency,
                billingCycle: s.billingCycle,
                startedAt: s.startedAt,
                endsAt: s.endsAt,
                lastPaymentAt: s.lastPaymentAt,
                failedPaymentCount: s.failedPaymentCount,
            })),
            pagination: { page: Number(page), limit: Number(limit), total, totalPages: Math.ceil(total / take) },
        }));
    }
    catch (e) {
        next(e);
    }
});
// ============================================================
// PAYMENT MANAGEMENT
// ============================================================
router.get('/payments', authenticateJWT, authorize(['MAIN_ADMIN']), async (req, res, next) => {
    try {
        const { status, page = 1, limit = 20 } = req.query;
        const skip = (Number(page) - 1) * Number(limit);
        const take = Number(limit);
        const where = {};
        if (status)
            where.paymentStatus = status;
        const [payments, total] = await Promise.all([
            prisma.payment.findMany({
                where,
                skip,
                take,
                orderBy: { createdAt: 'desc' },
                include: { account: { select: { businessName: true, ownerEmail: true } }, subscription: { include: { plan: true } } },
            }),
            prisma.payment.count({ where }),
        ]);
        res.json(ok({
            payments: payments.map(p => ({
                id: p.id,
                businessName: p.account.businessName,
                ownerEmail: p.account.ownerEmail,
                amount: p.amount,
                currency: p.currency,
                paymentMethod: p.paymentMethod,
                paymentReference: p.paymentReference,
                paymentStatus: p.paymentStatus,
                payerName: p.payerName,
                payerEmail: p.payerEmail,
                selectedPlan: p.selectedPlan,
                approvedBy: p.approvedBy,
                approvedAt: p.approvedAt,
                rejectedBy: p.rejectedBy,
                rejectedAt: p.rejectedAt,
                rejectionReason: p.rejectionReason,
                createdAt: p.createdAt,
            })),
            pagination: { page: Number(page), limit: Number(limit), total, totalPages: Math.ceil(total / take) },
        }));
    }
    catch (e) {
        next(e);
    }
});
router.post('/payments/approve', authenticateJWT, authorize(['MAIN_ADMIN']), validate(approvePaymentSchema), async (req, res, next) => {
    try {
        const { paymentId, action, rejectionReason } = req.body;
        const adminId = req.user.id;
        const payment = await prisma.payment.findUnique({
            where: { id: paymentId },
            include: { account: true, subscription: true },
        });
        if (!payment)
            throw new AppError(404, 'PAYMENT_NOT_FOUND', 'Payment not found');
        if (payment.paymentStatus !== 'PENDING')
            throw new AppError(400, 'PAYMENT_ALREADY_PROCESSED', 'Payment already processed');
        await prisma.$transaction(async (tx) => {
            if (action === 'approve') {
                await tx.payment.update({
                    where: { id: paymentId },
                    data: {
                        paymentStatus: 'COMPLETED',
                        approvedBy: adminId,
                        approvedAt: new Date(),
                    },
                });
                // Activate subscription
                if (payment.subscriptionId) {
                    await tx.subscription.update({
                        where: { id: payment.subscriptionId },
                        data: {
                            status: 'ACTIVE_SUBSCRIPTION',
                            startedAt: new Date(),
                            endsAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
                            lastPaymentAt: new Date(),
                            nextPaymentAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
                        },
                    });
                }
                await tx.account.update({
                    where: { id: payment.accountId },
                    data: {
                        subscriptionStatus: 'ACTIVE_SUBSCRIPTION',
                        subscriptionStartedAt: new Date(),
                        subscriptionEndsAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
                        paymentStatus: 'COMPLETED',
                        isLocked: false,
                        status: 'ACTIVE',
                    },
                });
                await tx.auditLog.create({
                    data: {
                        accountId: payment.accountId,
                        type: 'PAYMENT_APPROVED',
                        entityType: 'Payment',
                        entityId: paymentId,
                        metadata: { approvedBy: adminId, amount: payment.amount, plan: payment.selectedPlan },
                    },
                });
            }
            else {
                await tx.payment.update({
                    where: { id: paymentId },
                    data: {
                        paymentStatus: 'FAILED',
                        rejectedBy: adminId,
                        rejectedAt: new Date(),
                        rejectionReason: rejectionReason || 'Rejected by admin',
                    },
                });
                await tx.auditLog.create({
                    data: {
                        accountId: payment.accountId,
                        type: 'PAYMENT_REJECTED',
                        entityType: 'Payment',
                        entityId: paymentId,
                        metadata: { rejectedBy: adminId, reason: rejectionReason },
                    },
                });
            }
        });
        res.json(ok({ success: true, message: action === 'approve' ? 'Payment approved and subscription activated' : 'Payment rejected' }));
    }
    catch (e) {
        next(e);
    }
});
// ============================================================
// AUDIT LOGS
// ============================================================
router.get('/logs', authenticateJWT, authorize(['MAIN_ADMIN']), async (req, res, next) => {
    try {
        const { type, accountId, userId, page = 1, limit = 50, startDate, endDate } = req.query;
        const skip = (Number(page) - 1) * Number(limit);
        const take = Number(limit);
        const where = {};
        if (type)
            where.type = type;
        if (accountId)
            where.accountId = accountId;
        if (userId)
            where.userId = userId;
        if (startDate || endDate) {
            where.createdAt = {};
            if (startDate)
                where.createdAt.gte = new Date(String(startDate));
            if (endDate)
                where.createdAt.lte = new Date(String(endDate));
        }
        const [logs, total] = await Promise.all([
            prisma.auditLog.findMany({
                where,
                skip,
                take,
                orderBy: { createdAt: 'desc' },
                include: {
                    account: { select: { businessName: true, ownerEmail: true } },
                    user: { select: { email: true, name: true, role: true } },
                },
            }),
            prisma.auditLog.count({ where }),
        ]);
        res.json(ok({
            logs: logs.map(l => ({
                id: l.id,
                type: l.type,
                businessName: l.account?.businessName,
                ownerEmail: l.account?.ownerEmail,
                actorEmail: l.user?.email,
                actorName: l.user?.name,
                actorRole: l.user?.role,
                entityType: l.entityType,
                entityId: l.entityId,
                metadata: l.metadata,
                ipAddress: l.ipAddress,
                createdAt: l.createdAt,
            })),
            pagination: { page: Number(page), limit: Number(limit), total, totalPages: Math.ceil(total / take) },
        }));
    }
    catch (e) {
        next(e);
    }
});
// ============================================================
// REVENUE ANALYTICS
// ============================================================
router.get('/analytics/revenue', authenticateJWT, authorize(['MAIN_ADMIN']), async (req, res, next) => {
    try {
        const { period = '30d' } = req.query;
        const days = period === '7d' ? 7 : period === '30d' ? 30 : period === '90d' ? 90 : 365;
        const startDate = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
        const [dailyRevenue, packageBreakdown, totalRevenue] = await Promise.all([
            prisma.$queryRaw `
        SELECT DATE("createdAt") as date, SUM("amount") as revenue
        FROM "Payment"
        WHERE "paymentStatus" = 'COMPLETED' AND "createdAt" >= ${startDate}
        GROUP BY DATE("createdAt")
        ORDER BY DATE("createdAt") ASC
      `,
            prisma.payment.groupBy({
                by: ['selectedPlan'],
                where: { paymentStatus: 'COMPLETED', createdAt: { gte: startDate } },
                _sum: { amount: true },
                _count: true,
            }),
            prisma.payment.aggregate({
                where: { paymentStatus: 'COMPLETED', createdAt: { gte: startDate } },
                _sum: { amount: true },
            }),
        ]);
        res.json(ok({
            dailyRevenue,
            packageBreakdown: packageBreakdown.map(p => ({ plan: p.selectedPlan, revenue: p._sum.amount || 0, count: p._count })),
            totalRevenue: totalRevenue._sum.amount || 0,
            period: days,
        }));
    }
    catch (e) {
        next(e);
    }
});
// ============================================================
// MAIN ADMIN MANAGEMENT (Super Admin only)
// ============================================================
router.post('/admins', authenticateJWT, authorize(['MAIN_ADMIN']), validate(createMainAdminSchema), async (req, res, next) => {
    try {
        const { email, password, name } = req.body;
        const existing = await prisma.mainAdmin.findUnique({ where: { email } });
        if (existing)
            throw new AppError(409, 'EMAIL_TAKEN', 'Admin with this email already exists');
        const passwordHash = await bcrypt.hash(password, 12);
        const admin = await prisma.mainAdmin.create({
            data: { email, passwordHash, name },
        });
        res.status(201).json(ok({ admin: { id: admin.id, email: admin.email, name: admin.name, isActive: admin.isActive } }));
    }
    catch (e) {
        next(e);
    }
});
router.get('/admins', authenticateJWT, authorize(['MAIN_ADMIN']), async (_req, res, next) => {
    try {
        const admins = await prisma.mainAdmin.findMany({
            select: { id: true, email: true, name: true, isActive: true, lastLoginAt: true, createdAt: true },
            orderBy: { createdAt: 'desc' },
        });
        res.json(ok({ admins }));
    }
    catch (e) {
        next(e);
    }
});
// ============================================================
// PASSWORD RESET FOR MAIN ADMIN
// ============================================================
router.post('/admins/password-reset/request', async (req, res, next) => {
    try {
        const { email } = req.body;
        const admin = await prisma.mainAdmin.findUnique({ where: { email } });
        // Always return success to prevent email enumeration
        if (!admin)
            return res.json(ok({ success: true }));
        const resetToken = crypto.randomBytes(32).toString('hex');
        const resetTokenExpiry = new Date(Date.now() + 60 * 60 * 1000); // 1 hour
        await prisma.mainAdmin.update({
            where: { id: admin.id },
            data: { resetToken, resetTokenExpiry },
        });
        // TODO: Send email with reset token
        // For now, return token in response (dev only)
        res.json(ok({ success: true, resetToken: process.env.NODE_ENV === 'development' ? resetToken : undefined }));
    }
    catch (e) {
        next(e);
    }
});
router.post('/admins/password-reset/confirm', validate(resetPasswordSchema), async (req, res, next) => {
    try {
        const { email, newPassword, token } = req.body;
        const admin = await prisma.mainAdmin.findUnique({ where: { email } });
        if (!admin || !admin.resetToken || admin.resetToken !== token || admin.resetTokenExpiry < new Date()) {
            throw new AppError(400, 'INVALID_TOKEN', 'Invalid or expired reset token');
        }
        const passwordHash = await bcrypt.hash(newPassword, 12);
        await prisma.mainAdmin.update({
            where: { id: admin.id },
            data: { passwordHash, resetToken: null, resetTokenExpiry: null },
        });
        res.json(ok({ success: true, message: 'Password reset successful' }));
    }
    catch (e) {
        next(e);
    }
});
// Emergency super admin recovery endpoint
router.post('/emergency-recovery', async (req, res, next) => {
    try {
        const { email, password, secretKey } = req.body;
        // Verify emergency secret key from environment
        if (secretKey !== process.env.EMERGENCY_RECOVERY_KEY) {
            throw new AppError(403, 'INVALID_SECRET', 'Invalid recovery key');
        }
        const existing = await prisma.mainAdmin.findUnique({ where: { email } });
        if (existing) {
            // Update password
            const passwordHash = await bcrypt.hash(password, 12);
            await prisma.mainAdmin.update({
                where: { id: existing.id },
                data: { passwordHash, isActive: true },
            });
            return res.json(ok({ success: true, message: 'Super admin password updated' }));
        }
        // Create new super admin
        const passwordHash = await bcrypt.hash(password, 12);
        await prisma.mainAdmin.create({
            data: { email, passwordHash, name: 'Super Admin', isActive: true },
        });
        res.json(ok({ success: true, message: 'Super admin account created' }));
    }
    catch (e) {
        next(e);
    }
});
export default router;
