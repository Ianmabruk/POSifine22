import { Request, Response, NextFunction } from "express";
import { ProductsService } from "./products.service";
import { ok } from "../../utils/response";

export const ProductsController = {
  async list(_req: Request, res: Response, next: NextFunction) {
    try { res.json(ok(await ProductsService.list())); } catch (e) { next(e); }
  },
  async get(req: Request, res: Response, next: NextFunction) {
    try { res.json(ok(await ProductsService.get(req.params.id))); } catch (e) { next(e); }
  },
  async create(req: Request, res: Response, next: NextFunction) {
    try { res.status(201).json(ok(await ProductsService.create(req.body))); } catch (e) { next(e); }
  },
  async update(req: Request, res: Response, next: NextFunction) {
    try { res.json(ok(await ProductsService.update(req.params.id, req.body))); } catch (e) { next(e); }
  }
};
