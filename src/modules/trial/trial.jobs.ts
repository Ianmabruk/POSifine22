import { PrismaClient } from '@prisma/client';
import { logger } from '../../config/logger';
import { trialService } from './trial.service';

const prisma = new PrismaClient();

let trialCheckInterval: NodeJS.Timeout | null = null;

export function startTrialExpiryJob(intervalMs: number = 24 * 60 * 60 * 1000) {
  if (trialCheckInterval) {
    logger.warn('Trial expiry job already running');
    return;
  }

  trialCheckInterval = setInterval(async () => {
    try {
      const expired = await trialService.checkAndExpireTrials();
      if (expired.length > 0) {
        logger.info({ count: expired.length }, 'Expired trials locked');
      }
    } catch (error) {
      logger.error({ err: error }, 'Trial expiry check failed');
    }
  }, intervalMs);

  // Run once on startup after 5 seconds
  setTimeout(async () => {
    try {
      const expired = await trialService.checkAndExpireTrials();
      if (expired.length > 0) {
        logger.info({ count: expired.length }, 'Initial trial expiry check completed');
      }
    } catch (error) {
      logger.error({ err: error }, 'Initial trial expiry check failed');
    }
  }, 5000);

  logger.info({ intervalMs }, 'Trial expiry check job started');
}

export function stopTrialExpiryJob() {
  if (trialCheckInterval) {
    clearInterval(trialCheckInterval);
    trialCheckInterval = null;
    logger.info('Trial expiry check job stopped');
  }
}

// Daily at midnight - send trial expiry notifications
export function startTrialNotificationJob() {
  const checkNotifications = async () => {
    try {
      const expiringSoon = await trialService.getExpiringSoon(3);
      
      for (const account of expiringSoon) {
        const adminUser = account.users[0];
        if (adminUser) {
          const daysLeft = Math.ceil((account.trialEndsAt!.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
          
          await prisma.notification.create({
            data: {
              accountId: account.id,
              userId: adminUser.id,
              type: 'trial',
              title: 'Trial Expiring Soon',
              message: `Your free trial expires in ${daysLeft} day${daysLeft === 1 ? '' : 's'}. Subscribe now to continue using POSify.`,
              metadata: { trialEndsAt: account.trialEndsAt?.toISOString(), daysRemaining: daysLeft },
            },
          });
        }
      }
      
      if (expiringSoon.length > 0) {
        logger.info({ count: expiringSoon.length }, 'Trial expiry notifications sent');
      }
    } catch (error) {
      logger.error({ err: error }, 'Trial notification job failed');
    }
  };

  // Run daily at midnight
  const now = new Date();
  const midnight = new Date(now);
  midnight.setHours(24, 0, 0, 0);
  const msUntilMidnight = midnight.getTime() - now.getTime();

  setTimeout(() => {
    checkNotifications();
    setInterval(checkNotifications, 24 * 60 * 60 * 1000);
  }, msUntilMidnight);

  logger.info('Trial notification job scheduled for midnight');
}