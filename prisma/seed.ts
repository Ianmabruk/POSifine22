import { PrismaClient } from '@prisma/client';
import { mainAdminAuthService } from './main-admin.auth.service';

const prisma = new PrismaClient();

async function main() {
  console.log('🌱 Running database seed...');

  // Seed subscription plans
  console.log('📦 Seeding subscription plans...');
  
  const plans = [
    {
      name: 'STARTER',
      displayName: 'Starter',
      description: 'Perfect for small businesses getting started with POS',
      priceMonthly: 999,
      priceYearly: 9990,
      currency: 'KES',
      maxBranches: 1,
      maxCashiers: 2,
      maxProducts: 1000,
      hasAnalytics: false,
      hasReports: false,
      hasCustomerTracking: false,
      hasStaffManagement: false,
      hasApiAccess: false,
      hasPrioritySupport: false,
      hasMultiLocation: false,
      hasAdvancedAnalytics: false,
      sortOrder: 1,
    },
    {
      name: 'PROFESSIONAL',
      displayName: 'Professional',
      description: 'For growing businesses with multiple branches',
      priceMonthly: 2499,
      priceYearly: 24990,
      currency: 'KES',
      maxBranches: 10,
      maxCashiers: 10,
      maxProducts: -1,
      hasAnalytics: true,
      hasReports: true,
      hasCustomerTracking: true,
      hasStaffManagement: true,
      hasApiAccess: false,
      hasPrioritySupport: true,
      hasMultiLocation: true,
      hasAdvancedAnalytics: false,
      sortOrder: 2,
    },
    {
      name: 'ENTERPRISE',
      displayName: 'Enterprise',
      description: 'For large organizations with unlimited scale',
      priceMonthly: 4999,
      priceYearly: 49990,
      currency: 'KES',
      maxBranches: -1,
      maxCashiers: -1,
      maxProducts: -1,
      hasAnalytics: true,
      hasReports: true,
      hasCustomerTracking: true,
      hasStaffManagement: true,
      hasApiAccess: true,
      hasPrioritySupport: true,
      hasMultiLocation: true,
      hasAdvancedAnalytics: true,
      sortOrder: 3,
    },
  ];

  for (const plan of plans) {
    await prisma.subscriptionPlan.upsert({
      where: { name: plan.name },
      update: plan,
      create: plan,
    });
  }
  console.log('✅ Subscription plans seeded');

  // Seed super admin
  console.log('👤 Seeding super admin...');
  await mainAdminAuthService.seedSuperAdmin();
  console.log('✅ Super admin seeded');

  console.log('🎉 Database seed completed!');
}

main()
  .catch((e) => {
    console.error('❌ Seed failed:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });