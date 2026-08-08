import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcrypt';
import crypto from 'crypto';
import nodemailer from 'nodemailer';
import { AppError } from '../../utils/errors';
const prisma = new PrismaClient();
export class MainAdminAuthService {
    constructor() {
        this.emailTransporter = null;
        this.initEmailTransporter();
    }
    initEmailTransporter() {
        if (process.env.SENDGRID_API_KEY) {
            this.emailTransporter = nodemailer.createTransport({
                host: 'smtp.sendgrid.net',
                port: 587,
                secure: false,
                auth: {
                    user: 'apikey',
                    pass: process.env.SENDGRID_API_KEY,
                },
            });
        }
    }
    async requestPasswordReset(email) {
        const admin = await prisma.mainAdmin.findUnique({ where: { email } });
        // Always return success to prevent email enumeration
        if (!admin) {
            return { success: true };
        }
        const resetToken = crypto.randomBytes(32).toString('hex');
        const resetTokenExpiry = new Date(Date.now() + 60 * 60 * 1000); // 1 hour
        await prisma.mainAdmin.update({
            where: { id: admin.id },
            data: { resetToken, resetTokenExpiry },
        });
        // Send email if transporter is configured
        if (this.emailTransporter && process.env.FROM_EMAIL) {
            try {
                const resetUrl = `${process.env.FRONTEND_URL}/main-admin/reset-password?token=${resetToken}&email=${encodeURIComponent(email)}`;
                await this.emailTransporter.sendMail({
                    from: `"POSify" <${process.env.FROM_EMAIL}>`,
                    to: email,
                    subject: 'POSify Control Center - Password Reset Request',
                    html: `
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
              <div style="background: linear-gradient(135deg, #FF7A00 0%, #4FC3F7 100%); padding: 24px; border-radius: 12px 12px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 24px;">POSify Control Center</h1>
              </div>
              <div style="background: #f8fafc; padding: 24px; border-radius: 0 0 12px 12px; border: 1px solid #e2e8f0;">
                <p style="color: #334155; font-size: 16px; line-height: 1.6;">Hello ${admin.name},</p>
                <p style="color: #334155; font-size: 16px; line-height: 1.6;">You requested a password reset for your POSify Control Center account. Click the button below to create a new password:</p>
                <div style="text-align: center; margin: 32px 0;">
                  <a href="${resetUrl}" style="display: inline-block; background: linear-gradient(135deg, #FF7A00 0%, #4FC3F7 100%); color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 16px;">Reset Password</a>
                </div>
                <p style="color: #64748b; font-size: 14px; line-height: 1.6;">This link will expire in 1 hour. If you didn't request this reset, please ignore this email or contact support.</p>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
                <p style="color: #94a3b8; font-size: 12px;">If the button doesn't work, copy this link: ${resetUrl}</p>
              </div>
            </div>
          `,
                });
            }
            catch (emailError) {
                console.error('Failed to send password reset email:', emailError);
            }
        }
        // In development, return token for testing
        if (process.env.NODE_ENV === 'development') {
            return { success: true, resetToken };
        }
        return { success: true };
    }
    async confirmPasswordReset(email, token, newPassword) {
        const admin = await prisma.mainAdmin.findUnique({ where: { email } });
        if (!admin || !admin.resetToken || admin.resetToken !== token) {
            throw new AppError(400, 'INVALID_TOKEN', 'Invalid or expired reset token');
        }
        if (!admin.resetTokenExpiry || admin.resetTokenExpiry < new Date()) {
            throw new AppError(400, 'TOKEN_EXPIRED', 'Reset token has expired');
        }
        const passwordHash = await bcrypt.hash(newPassword, 12);
        await prisma.mainAdmin.update({
            where: { id: admin.id },
            data: {
                passwordHash,
                resetToken: null,
                resetTokenExpiry: null,
            },
        });
        await prisma.auditLog.create({
            data: {
                type: 'PASSWORD_RESET',
                entityType: 'MainAdmin',
                entityId: admin.id,
                metadata: { email: admin.email },
            },
        });
        return { success: true, message: 'Password reset successful' };
    }
    async emergencyRecovery(email, password, secretKey) {
        // Verify emergency recovery key
        const expectedKey = process.env.EMERGENCY_RECOVERY_KEY;
        if (!expectedKey || secretKey !== expectedKey) {
            throw new AppError(403, 'INVALID_SECRET', 'Invalid recovery key');
        }
        const existing = await prisma.mainAdmin.findUnique({ where: { email } });
        const passwordHash = await bcrypt.hash(password, 12);
        if (existing) {
            await prisma.mainAdmin.update({
                where: { id: existing.id },
                data: { passwordHash, isActive: true },
            });
            return { success: true, message: 'Super admin password updated', created: false };
        }
        await prisma.mainAdmin.create({
            data: { email, passwordHash, name: 'Super Admin', isActive: true },
        });
        return { success: true, message: 'Super admin account created', created: true };
    }
    async seedSuperAdmin() {
        const email = process.env.SUPER_ADMIN_EMAIL || process.env.MAIN_ADMIN_EMAIL;
        const password = process.env.SUPER_ADMIN_PASSWORD || process.env.MAIN_ADMIN_PASSWORD;
        const name = process.env.SUPER_ADMIN_NAME || 'Super Admin';
        if (!email || !password) {
            console.warn('Super admin credentials not configured in environment');
            return null;
        }
        const existing = await prisma.mainAdmin.findUnique({ where: { email } });
        if (existing) {
            // Update password if env has changed
            const passwordHash = await bcrypt.hash(password, 12);
            await prisma.mainAdmin.update({
                where: { id: existing.id },
                data: { passwordHash, isActive: true, name },
            });
            console.log(`Super admin updated: ${email}`);
            return existing;
        }
        const passwordHash = await bcrypt.hash(password, 12);
        const admin = await prisma.mainAdmin.create({
            data: { email, passwordHash, name, isActive: true },
        });
        console.log(`Super admin created: ${email}`);
        return admin;
    }
}
export const mainAdminAuthService = new MainAdminAuthService();
