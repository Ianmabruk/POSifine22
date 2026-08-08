import { PrismaClient } from '@prisma/client';
import { AppError } from '../../utils/errors';
const prisma = new PrismaClient();
export const SubscriptionPlans = {
    STARTER: {
        name: 'STARTER',
        displayName: 'Starter',
        description: 'Perfect for small businesses getting started with POS',
        priceMonthly: 999,
        priceYearly: 9990,
        currency: 'KES',
        features: {
            maxBranches: 1,
            maxCashiers: 2,
            maxProducts: 1000,
            hasAnalytics: false,
            hasReports: false,
            hasCustomerTracking: false,
            hasStaffManagement: false,
            hasApiAccess: false,
            hasPrioritySupport: false,
            hasMultiLocation: false,
            hasAdvancedAnalytics: false,
        },
    },
    PROFESSIONAL: {
        name: 'PROFESSIONAL',
        displayName: 'Professional',
        description: 'For growing businesses with multiple branches',
        priceMonthly: 2499,
        priceYearly: 24990,
        currency: 'KES',
        features: {
            maxBranches: 10,
            maxCashiers: 10,
            maxProducts: -1,
            hasAnalytics: true,
            hasReports: true,
            hasCustomerTracking: true,
            hasStaffManagement: true,
            hasApiAccess: false,
            hasPrioritySupport: true,
            hasMultiLocation: true,
            hasAdvancedAnalytics: false,
        },
    },
    ENTERPRISE: {
        name: 'ENTERPRISE',
        displayName: 'Enterprise',
        description: 'For large organizations with unlimited scale',
        priceMonthly: 4999,
        priceYearly: 49990,
        currency: 'KES',
        features: {
            maxBranches: -1,
            maxCashiers: -1,
            maxProducts: -1,
            hasAnalytics: true,
            hasReports: true,
            hasCustomerTracking: true,
            hasStaffManagement: true,
            hasApiAccess: true,
            hasPrioritySupport: true,
            hasMultiLocation: true,
            hasAdvancedAnalytics: true,
        },
    },
};
export class SubscriptionService {
    async getPlans() {
        return Object.values(SubscriptionPlans).map(plan => ({
            id: plan.name.toLowerCase(),
            name: plan.name,
            displayName: plan.displayName,
            description: plan.description,
            priceMonthly: plan.priceMonthly,
            priceYearly: plan.priceYearly,
            currency: plan.currency,
            features: plan.features,
        }));
    }
    async getPlanByName(planName) {
        const plan = SubscriptionPlans[planName.toUpperCase()];
        if (!plan) {
            throw new AppError(404, 'PLAN_NOT_FOUND', 'Subscription plan not found');
        }
        return plan;
    }
    async createTrialSubscription(accountId, planName) {
        const plan = await this.getPlanByName(planName);
        const trialEndsAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
        const subscription = await prisma.subscription.create({
            data: {
                accountId,
                planId: plan.name,
                status: 'ACTIVE_TRIAL',
                trialStartedAt: new Date(),
                trialEndsAt: trialEndsAt,
                billingCycle: 'monthly',
                amount: plan.priceMonthly,
                currency: plan.currency,
            },
            include: { plan: true },
        });
        // Update account status
        await prisma.account.update({
            where: { id: accountId },
            data: {
                plan: plan.name,
                subscriptionStatus: 'ACTIVE_TRIAL',
                trialStartedAt: new Date(),
                trialEndsAt: trialEndsAt,
                trialStatus: 'ACTIVE',
                status: 'TRIAL',
            },
        });
        // Create trial record
        await prisma.trial.create({
            data: {
                accountId,
                status: 'ACTIVE',
                plan: plan.name,
                startedAt: new Date(),
                endsAt: trialEndsAt,
            },
        });
        // Log audit
        await prisma.auditLog.create({
            data: {
                accountId,
                type: 'TRIAL_STARTED',
                entityType: 'Subscription',
                entityId: subscription.id,
                metadata: { plan: plan.name, trialEndsAt: trialEndsAt.toISOString() },
            },
        });
        return subscription;
    }
    async getSubscriptionByAccount(accountId) {
        return prisma.subscription.findFirst({
            where: { accountId },
            include: { plan: true, payments: { orderBy: { createdAt: 'desc' } } },
        });
    }
    async checkTrialExpiry() {
        const expiredTrials = await prisma.subscription.findMany({
            where: {
                status: 'ACTIVE_TRIAL',
                trialEndsAt: { lt: new Date() },
            },
            include: { account: true },
        });
        for (const sub of expiredTrials) {
            await this.expireTrial(sub.id);
        }
        return expiredTrials;
    }
    async expireTrial(subscriptionId) {
        const subscription = await prisma.subscription.findUnique({
            where: { id: subscriptionId },
            include: { account: true },
        });
        if (!subscription)
            throw new AppError(404, 'SUBSCRIPTION_NOT_FOUND', 'Subscription not found');
        await prisma.$transaction(async (tx) => {
            // Update subscription
            await tx.subscription.update({
                where: { id: subscriptionId },
                data: { status: 'TRIAL_EXPIRED' },
            });
            // Update account
            await tx.account.update({
                where: { id: subscription.accountId },
                data: {
                    subscriptionStatus: 'TRIAL_EXPIRED',
                    trialStatus: 'EXPIRED',
                    isLocked: true,
                    status: 'LOCKED',
                },
            });
            // Update trial record
            await tx.trial.update({
                where: { accountId: subscription.accountId },
                data: { status: 'EXPIRED' },
            });
            // Log audit
            await tx.auditLog.create({
                data: {
                    accountId: subscription.accountId,
                    type: 'TRIAL_EXPIRED',
                    entityType: 'Subscription',
                    entityId: subscriptionId,
                },
            });
        });
        return { success: true };
    }
    async extendTrial(subscriptionId, days, extendedBy, reason) {
        const subscription = await prisma.subscription.findUnique({
            where: { id: subscriptionId },
            include: { account: true },
        });
        if (!subscription)
            throw new AppError(404, 'SUBSCRIPTION_NOT_FOUND', 'Subscription not found');
        const newTrialEndsAt = new Date(subscription.trialEndsAt.getTime() + days * 24 * 60 * 60 * 1000);
        await prisma.$transaction(async (tx) => {
            await tx.subscription.update({
                where: { id: subscriptionId },
                data: { trialEndsAt: newTrialEndsAt },
            });
            await tx.account.update({
                where: { id: subscription.accountId },
                data: {
                    trialEndsAt: newTrialEndsAt,
                    trialExtendedAt: new Date(),
                    trialExtendedBy: extendedBy,
                    trialExtensionReason: reason,
                    trialStatus: 'EXTENDED',
                },
            });
            await tx.trial.update({
                where: { accountId: subscription.accountId },
                data: {
                    status: 'EXTENDED',
                    extendedAt: new Date(),
                    extendedBy,
                    extensionReason: reason,
                    endsAt: newTrialEndsAt,
                },
            });
            await tx.auditLog.create({
                data: {
                    accountId: subscription.accountId,
                    type: 'TRIAL_EXTENDED',
                    entityType: 'Subscription',
                    entityId: subscriptionId,
                    metadata: { extendedBy, reason, days, newEndDate: newTrialEndsAt.toISOString() },
                },
            });
        });
        return { success: true, newTrialEndsAt };
    }
    async convertTrialToSubscription(subscriptionId, billingCycle) {
        const subscription = await prisma.subscription.findUnique({
            where: { id: subscriptionId },
            include: { plan: true, account: true },
        });
        if (!subscription)
            throw new AppError(404, 'SUBSCRIPTION_NOT_FOUND', 'Subscription not found');
        const amount = billingCycle === 'yearly' ? (subscription.plan.priceYearly || subscription.plan.priceMonthly * 12) : subscription.plan.priceMonthly;
        const endsAt = new Date(Date.now() + (billingCycle === 'yearly' ? 365 : 30) * 24 * 60 * 60 * 1000);
        await prisma.$transaction(async (tx) => {
            await tx.subscription.update({
                where: { id: subscriptionId },
                data: {
                    status: 'ACTIVE_SUBSCRIPTION',
                    startedAt: new Date(),
                    endsAt,
                    billingCycle,
                    amount,
                    trialEndsAt: null,
                },
            });
            await tx.account.update({
                where: { id: subscription.accountId },
                data: {
                    subscriptionStatus: 'ACTIVE_SUBSCRIPTION',
                    subscriptionStartedAt: new Date(),
                    subscriptionEndsAt: endsAt,
                    subscriptionPlan: subscription.plan.name,
                    paymentStatus: 'COMPLETED',
                    isLocked: false,
                    status: 'ACTIVE',
                    trialStatus: 'CONVERTED',
                },
            });
            await tx.trial.update({
                where: { accountId: subscription.accountId },
                data: { status: 'CONVERTED', convertedAt: new Date() },
            });
            await tx.auditLog.create({
                data: {
                    accountId: subscription.accountId,
                    type: 'SUBSCRIPTION_CREATED',
                    entityType: 'Subscription',
                    entityId: subscriptionId,
                    metadata: { plan: subscription.plan.name, billingCycle, amount, endsAt: endsAt.toISOString() },
                },
            });
        });
        return { success: true, endsAt };
    }
    async createPendingPayment(data) {
        const payment = await prisma.payment.create({
            data: {
                ...data,
                paymentMethod: data.paymentMethod,
                paymentStatus: 'PENDING',
            },
        });
        await prisma.subscription.update({
            where: { id: data.subscriptionId },
            data: { status: 'PENDING_PAYMENT' },
        });
        await prisma.account.update({
            where: { id: data.accountId },
            data: { paymentStatus: 'PENDING' },
        });
        await prisma.auditLog.create({
            data: {
                accountId: data.accountId,
                type: 'PAYMENT_SUBMITTED',
                entityType: 'Payment',
                entityId: payment.id,
                metadata: { amount: data.amount, method: data.paymentMethod, reference: data.paymentReference },
            },
        });
        return payment;
    }
    async approvePayment(paymentId, approvedBy) {
        const payment = await prisma.payment.findUnique({
            where: { id: paymentId },
            include: { subscription: { include: { plan: true, account: true } } },
        });
        if (!payment)
            throw new AppError(404, 'PAYMENT_NOT_FOUND', 'Payment not found');
        await prisma.$transaction(async (tx) => {
            await tx.payment.update({
                where: { id: paymentId },
                data: { paymentStatus: 'COMPLETED', approvedBy, approvedAt: new Date() },
            });
            await tx.subscription.update({
                where: { id: payment.subscriptionId },
                data: {
                    status: 'ACTIVE_SUBSCRIPTION',
                    startedAt: new Date(),
                    endsAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
                },
            });
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
                    metadata: { approvedBy, amount: payment.amount },
                },
            });
        });
        return { success: true };
    }
    async rejectPayment(paymentId, rejectedBy, reason) {
        const payment = await prisma.payment.findUnique({
            where: { id: paymentId },
            include: { subscription: { include: { account: true } } },
        });
        if (!payment)
            throw new AppError(404, 'PAYMENT_NOT_FOUND', 'Payment not found');
        await prisma.$transaction(async (tx) => {
            await tx.payment.update({
                where: { id: paymentId },
                data: { paymentStatus: 'FAILED', rejectedBy, rejectedAt: new Date(), rejectionReason: reason },
            });
            await tx.subscription.update({
                where: { id: payment.subscriptionId },
                data: { status: 'TRIAL_EXPIRED' },
            });
            await tx.account.update({
                where: { id: payment.accountId },
                data: { paymentStatus: 'FAILED' },
            });
            await tx.auditLog.create({
                data: {
                    accountId: payment.accountId,
                    type: 'PAYMENT_REJECTED',
                    entityType: 'Payment',
                    entityId: paymentId,
                    metadata: { rejectedBy, reason, amount: payment.amount },
                },
            });
        });
        return { success: true };
    }
    async suspendSubscription(subscriptionId) {
        const subscription = await prisma.subscription.findUnique({
            where: { id: subscriptionId },
            include: { account: true },
        });
        if (!subscription)
            throw new AppError(404, 'SUBSCRIPTION_NOT_FOUND', 'Subscription not found');
        await prisma.$transaction(async (tx) => {
            await tx.subscription.update({
                where: { id: subscriptionId },
                data: { status: 'SUSPENDED' },
            });
            await tx.account.update({
                where: { id: subscription.accountId },
                data: { subscriptionStatus: 'SUSPENDED', isLocked: true, status: 'SUSPENDED' },
            });
            await tx.auditLog.create({
                data: {
                    accountId: subscription.accountId,
                    type: 'SUBSCRIPTION_SUSPENDED',
                    entityType: 'Subscription',
                    entityId: subscriptionId,
                },
            });
        });
        return { success: true };
    }
    async reactivateSubscription(subscriptionId) {
        const subscription = await prisma.subscription.findUnique({
            where: { id: subscriptionId },
            include: { account: true },
        });
        if (!subscription)
            throw new AppError(404, 'SUBSCRIPTION_NOT_FOUND', 'Subscription not found');
        await prisma.$transaction(async (tx) => {
            await tx.subscription.update({
                where: { id: subscriptionId },
                data: { status: 'ACTIVE_SUBSCRIPTION' },
            });
            await tx.account.update({
                where: { id: subscription.accountId },
                data: { subscriptionStatus: 'ACTIVE_SUBSCRIPTION', isLocked: false, status: 'ACTIVE' },
            });
            await tx.auditLog.create({
                data: {
                    accountId: subscription.accountId,
                    type: 'SUBSCRIPTION_REACTIVATED',
                    entityType: 'Subscription',
                    entityId: subscriptionId,
                },
            });
        });
        return { success: true };
    }
    async getSubscriptionStats() {
        const [totalBusinesses, activeSubscriptions, expiredTrials, pendingPayments, suspendedSubscriptions, totalRevenue,] = await Promise.all([
            prisma.account.count(),
            prisma.subscription.count({ where: { status: 'ACTIVE_SUBSCRIPTION' } }),
            prisma.subscription.count({ where: { status: 'TRIAL_EXPIRED' } }),
            prisma.payment.count({ where: { paymentStatus: 'PENDING' } }),
            prisma.subscription.count({ where: { status: 'SUSPENDED' } }),
            prisma.payment.aggregate({
                where: { paymentStatus: 'COMPLETED' },
                _sum: { amount: true },
            }),
        ]);
        const monthlyGrowth = await prisma.account.groupBy({
            by: ['createdAt'],
            where: { createdAt: { gte: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000) } },
            _count: true,
        });
        return {
            totalBusinesses,
            activeSubscriptions,
            expiredTrials,
            pendingPayments,
            suspendedSubscriptions,
            totalRevenue: totalRevenue._sum.amount || 0,
            monthlyGrowth: monthlyGrowth.length,
        };
    }
}
