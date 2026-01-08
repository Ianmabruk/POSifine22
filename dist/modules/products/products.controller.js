import { ProductsService } from "./products.service";
import { ok } from "../../utils/response";
export const ProductsController = {
    async list(_req, res, next) {
        try {
            res.json(ok(await ProductsService.list()));
        }
        catch (e) {
            next(e);
        }
    },
    async get(req, res, next) {
        try {
            res.json(ok(await ProductsService.get(req.params.id)));
        }
        catch (e) {
            next(e);
        }
    },
    async create(req, res, next) {
        try {
            res.status(201).json(ok(await ProductsService.create(req.body)));
        }
        catch (e) {
            next(e);
        }
    },
    async update(req, res, next) {
        try {
            res.json(ok(await ProductsService.update(req.params.id, req.body)));
        }
        catch (e) {
            next(e);
        }
    }
};
