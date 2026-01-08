import { z } from "zod";

export const signupSchema = z.object({
  body: z.object({
    email: z.string().email(),
    password: z.string().min(6),
    role: z.enum(["ADMIN", "CASHIER"]).default("CASHIER"),
    deviceId: z.string().min(3).default("unknown")
  })
});

export const loginSchema = z.object({
  body: z.object({
    email: z.string().email(),
    password: z.string().min(6),
    deviceId: z.string().min(3)
  })
});

export const refreshSchema = z.object({
  body: z.object({
    refreshToken: z.string().min(10),
    deviceId: z.string().min(3)
  })
});
