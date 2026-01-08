import { sqlite } from "../../database/sqlite/client";
export const ProductsRepo = {
    list() { return sqlite.product.findMany({ orderBy: { updatedAt: "desc" } }); },
    get(id) { return sqlite.product.findUnique({ where: { id } }); },
    async create(data) {
        return sqlite.$transaction(async (tx) => {
            const product = await tx.product.create({ data: { ...data, status: "ACTIVE", version: 1, syncStatus: "PENDING" } });
            await tx.syncQueue.create({ data: { entityType: "Product", entityId: product.id, operation: "UPSERT" } });
            return product;
        });
    },
    async update(id, data) {
        return sqlite.$transaction(async (tx) => {
            const updated = await tx.product.update({ where: { id }, data: { ...data, version: { increment: 1 }, syncStatus: "PENDING" } });
            await tx.syncQueue.create({ data: { entityType: "Product", entityId: id, operation: "UPSERT" } });
            return updated;
        });
    }
};
