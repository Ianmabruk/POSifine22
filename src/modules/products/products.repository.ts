import { sqlite } from "../../database/sqlite/client";

export const ProductsRepo = {
  list() { return sqlite.product.findMany({ orderBy: { updatedAt: "desc" } }); },
  get(id: string) { return sqlite.product.findUnique({ where: { id } }); },
  async create(data: { sku: string; name: string; category?: string; costPrice: string; sellingPrice: string; quantity: number; }) {
    return sqlite.$transaction(async (tx) => {
      const product = await tx.product.create({ data: { ...data, status: "ACTIVE", version: 1, syncStatus: "PENDING" as any } });
      await tx.syncQueue.create({ data: { entityType: "Product", entityId: product.id, operation: "UPSERT" as any } });
      return product;
    });
  },
  async update(id: string, data: Partial<{ name: string; category?: string; costPrice: string; sellingPrice: string; quantity: number; status: "ACTIVE"|"INACTIVE"; }>) {
    return sqlite.$transaction(async (tx) => {
      const updated = await tx.product.update({ where: { id }, data: { ...data, version: { increment: 1 }, syncStatus: "PENDING" as any } });
      await tx.syncQueue.create({ data: { entityType: "Product", entityId: id, operation: "UPSERT" as any } });
      return updated;
    });
  }
};
