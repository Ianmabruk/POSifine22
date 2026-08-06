import { Request, Response, NextFunction } from 'express';
import { PrismaClient } from '@prisma/client';
import { AuthRequest } from './auth';

const prisma = new PrismaClient();

export const trialEnforcementMiddleware = async (
  req: AuthRequest,
  res: Response,
  next: NextFunction
) => {
  // Skip for non-authenticated routes
  if (!req.user) return next();

  // Skip for main admin
  if (req.user.role === 'main_admin') return next();

  // Skip for subscription-related routes
  const path = req.path;
  if (
    path.startsWith('/api/v1/subscription') ||
    path.startsWith('/api/v1/auth') ||
    path === '/api/v1/health'
  ) {
    return next();
  }

  try {
    const accountId = req.user.accountId;
    
    // Get account with subscription info
    const account = await prisma.account.findUnique({
      where: { id: accountId },
      include: { subscriptions: { include: { plan: true } } },
    });

    if (!account) {
      return res.status(404).json({ error: 'Account not found' });
    }

    // Check trial expiry
    if (account.trialEndsAt && new Date() > account.trialEndsAt) {
      // Auto-expire trial if not already expired
      if (account.subscriptionStatus === 'ACTIVE_TRIAL') {
        await expireTrial(accountId);
      }
      
      // Return trial expired response
      return res.status(403).json({
        success: false,
        error: 'TRIAL_EXPIRED',
        message: 'Your free trial has expired. Please subscribe to continue using POSify.',
        code: 'TRIAL_EXPIRED',
        trialEndedAt: account.trialEndsAt,
      });
    }

    // Check if account is locked
    if (account.isLocked || account.status === 'LOCKED') {
      return res.status(403).json({
        success: false,
        error: 'ACCOUNT_LOCKED',
        message: 'Your account is locked. Please contact support or subscribe to unlock.',
        code: 'ACCOUNT_LOCKED',
      });
    }

    // Check subscription status for non-trial accounts
    if (account.subscriptionStatus !== 'ACTIVE_TRIAL' && account.subscriptionStatus !== 'ACTIVE_SUBSCRIPTION') {
      return res.status(403).json({
        success: false,
        error: 'SUBSCRIPTION_REQUIRED',
        message: 'Active subscription required to access this resource.',
        code: 'SUBSCRIPTION_REQUIRED',
        subscriptionStatus: account.subscriptionStatus,
      });
    }

    // Attach account info to request for use in controllers
    req.account = account;
    next();
  } catch (error) {
    console.error('Trial enforcement error:', error);
    next(error);
  }
};

async function expireTrial(accountId: string) {
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
}

export const checkTrialExpiryJob = async () => {
  const expiredAccounts = await prisma.account.findMany({
    where: {
      trialEndsAt: { lt: new Date() },
      subscriptionStatus: 'ACTIVE_TRIAL',
    },
    select: { id: true },
  });

  for (const account of expiredAccounts) {
    await expireTrial(account.id);
  }

  return expiredAccounts.length;
};

// Check trial status for display
export const getTrialStatus = async (accountId: string) => {
  const account = await prisma.account.findUnique({
    where: { id: accountId },
    include: { subscriptions: { include: { plan: true } }, trial: true },
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
};