import { z } from "zod";

export const createProductSchema = z.object({
  body: z.object({
    sku: z.string().min(1),
    name: z.string().min(1),
    category: z.string().optional(),
    costPrice: z.string().regex(/^\d+\.?\d{0,2}$/),
    sellingPrice: z.string().regex(/^\d+\.?\d{0,2}$/),
    quantity: z.number().int().min(0)
  })
});

export const updateProductSchema = z.object({
  body: z.object({
    name: z.string().min(1).optional(),
    category: z.string().optional(),
    costPrice: z.string().regex(/^\d+\.?\d{0,2}$/).optional(),
    sellingPrice: z.string().regex(/^\d+\.?\d{0,2}$/).optional(),
    quantity: z.number().int().min(0).optional(),
    status: z.enum(["ACTIVE", "INACTIVE"]).optional()
  }),
  params: z.object({ id: z.string().uuid() })
});
