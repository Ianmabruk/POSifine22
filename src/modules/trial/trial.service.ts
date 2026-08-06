import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export class TrialService {
  async checkAndExpireTrials() {
    const expiredAccounts = await prisma.account.findMany({
      where: {
        trialEndsAt: { lt: new Date() },
        subscriptionStatus: 'ACTIVE_TRIAL',
      },
      select: { id: true },
    });

    for (const account of expiredAccounts) {
      await this.expireTrial(account.id);
    }

    return expiredAccounts;
  }

  async expireTrial(accountId: string) {
    const subscription = await prisma.subscription.findFirst({
      where: { accountId, status: 'ACTIVE_TRIAL' },
    });

    if (subscription) {
      await prisma.$transaction(async (tx) => {
        await tx.subscription.update({
          where: { id: subscription.id },
          data: { status: 'TRIAL_EXPIRED' },
        });

        await tx.account.update({
          where: { id: accountId },
          data: {
            subscriptionStatus: 'TRIAL_EXPIRED',
            trialStatus: 'EXPIRED',
            isLocked: true,
            status: 'LOCKED',
          },
        });

        await tx.trial.update({
          where: { accountId },
          data: { status: 'EXPIRED' },
        });

        await tx.auditLog.create({
          data: {
            accountId,
            type: 'TRIAL_EXPIRED',
            entityType: 'Subscription',
            entityId: subscription.id,
          },
        });
      });
    }

    return { success: true };
  }

  async getExpiringSoon(days: number = 3) {
    const cutoffDate = new Date(Date.now() + days * 24 * 60 * 60 * 1000);
    
    return prisma.account.findMany({
      where: {
        trialEndsAt: {
          gte: new Date(),
          lte: cutoffDate,
        },
        subscriptionStatus: 'ACTIVE_TRIAL',
        isLocked: false,
      },
      include: {
        users: { where: { role: 'ADMIN' }, take: 1 },
      },
    });
  }

  async getTrialStatus(accountId: string) {
    const account = await prisma.account.findUnique({
      where: { id: accountId },
      include: {
        subscriptions: { include: { plan: true } },
        trial: true,
      },
    });

    if (!account) return null;

    const now = new Date();
    const trialEndsAt = account.trialEndsAt;
    let daysRemaining = 0;
    let isExpired = false;
    let isExpiringSoon = false;

    if (trialEndsAt) {
      const diffTime = trialEndsAt.getTime() - now.getTime();
      daysRemaining = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
      isExpired = daysRemaining <= 0;
      isExpiringSoon = daysRemaining <= 3 && daysRemaining > 0;
    }

    return {
      isTrialActive: account.subscriptionStatus === 'ACTIVE_TRIAL',
      trialEndsAt: account.trialEndsAt,
      daysRemaining: Math.max(0, daysRemaining),
      isExpired,
      isExpiringSoon,
      subscriptionStatus: account.subscriptionStatus,
      plan: account.subscriptions[0]?.plan?.name || account.plan,
      hasActiveSubscription: account.subscriptionStatus === 'ACTIVE_SUBSCRIPTION',
    };
  }

  async extendTrial(accountId: string, days: number, extendedBy: string, reason: string) {
    const trial = await prisma.trial.findUnique({ where: { accountId }, include: { account: true } });
    if (!trial) throw new Error('Trial not found for this account');

    const newEndsAt = new Date(trial.endsAt.getTime() + days * 24 * 60 * 60 * 1000);

    await prisma.$transaction(async (tx) => {
      await tx.trial.update({
        where: { id: trial.id },
        data: {
          status: 'EXTENDED',
          endsAt: newEndsAt,
          extendedAt: new Date(),
          extendedBy,
          extensionReason: reason,
        },
      });

      await tx.account.update({
        where: { id: accountId },
        data: {
          trialEndsAt: newEndsAt,
          trialExtendedAt: new Date(),
          trialExtendedBy: extendedBy,
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
          metadata: { extendedBy, reason, days, newEndDate: newEndsAt.toISOString() },
        },
      });
    });

    return { success: true, newTrialEndsAt: newEndsAt };
  }

  async getExpiredTrials() {
    return prisma.account.findMany({
      where: {
        trialEndsAt: { lt: new Date() },
        subscriptionStatus: { in: ['ACTIVE_TRIAL', 'TRIAL_EXPIRED'] },
      },
      include: { subscriptions: { include: { plan: true } } },
    });
  }
}

export const trialService = new TrialService();