import { Request, Response, NextFunction } from "express";
import { AppError } from "../utils/errors";
import { logger } from "../config/logger";
import { fail } from "../utils/response";

export function errorHandler(err: unknown, _req: Request, res: Response, _next: NextFunction) {
  if (err instanceof AppError) {
    logger.warn({ code: err.code, details: err.details }, err.message);
    return res.status(err.status).json(fail(err.status, err.code, err.message, err.details));
  }
  logger.error({ err }, "Unhandled error");
  return res.status(500).json(fail(500, "INTERNAL_SERVER_ERROR", "Unexpected error"));
}
