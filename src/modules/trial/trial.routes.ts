import { Router } from 'express';
import { z } from 'zod';
import { validate } from '../../middlewares/validate';
import { authenticateJWT, authorize, AuthRequest } from '../../middlewares/auth';
import { trialService } from './trial.service';
import { ok } from '../../utils/response';
import { AppError } from '../../utils/errors';

const router = Router();

const extendTrialSchema = z.object({
  body: z.object({
    accountId: z.string().uuid(),
    days: z.number().int().min(1).max(365),
    reason: z.string().min(1).max(500),
  }),
});

const checkTrialSchema = z.object({
  query: z.object({
    accountId: z.string().uuid().optional(),
  }),
});

// Public/Authenticated routes
router.get('/status', authenticateJWT, async (req: AuthRequest, res, next) => {
  try {
    const accountId = req.user!.accountId;
    const status = await trialService.getTrialStatus(accountId);
    res.json(ok(status));
  } catch (e) { next(e); }
});

// Main Admin routes
router.get('/admin/expiring', authenticateJWT, authorize(['MAIN_ADMIN']), async (_req, res, next) => {
  try {
    const trials = await trialService.getExpiringSoon();
    res.json(ok(trials));
  } catch (e) { next(e); }
});

router.get('/admin/expired', authenticateJWT, authorize(['MAIN_ADMIN']), async (_req, res, next) => {
  try {
    const trials = await trialService.getExpiredTrials();
    res.json(ok(trials));
  } catch (e) { next(e); }
});

router.post('/admin/extend', authenticateJWT, authorize(['MAIN_ADMIN']), validate(extendTrialSchema), async (req: AuthRequest, res, next) => {
  try {
    const { accountId, days, reason } = req.body;
    const result = await trialService.extendTrial(accountId, days, req.user!.id, reason);
    res.json(ok(result));
  } catch (e) { next(e); }
});

router.post('/admin/check-expiry', authenticateJWT, authorize(['MAIN_ADMIN']), async (_req, res, next) => {
  try {
    const expired = await trialService.checkAndExpireTrials();
    res.json(ok({ expiredCount: expired.length, expired }));
  } catch (e) { next(e); }
});

export default router;