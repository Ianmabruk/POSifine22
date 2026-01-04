# PostgreSQL Setup for Vercel Deployment

## Option 1: Neon (Recommended - Free Tier)

1. Go to [neon.tech](https://neon.tech) and create account
2. Create new project
3. Copy connection string (looks like: `postgresql://username:password@host/database?sslmode=require`)
4. Add to Vercel environment variables as `DATABASE_URL`

## Option 2: Supabase (Alternative)

1. Go to [supabase.com](https://supabase.com) and create account
2. Create new project
3. Go to Settings > Database
4. Copy connection string
5. Add to Vercel environment variables as `DATABASE_URL`

## Vercel Environment Variables

Add these to your Vercel project settings:

```
DATABASE_URL=postgresql://your-connection-string
JWT_SECRET=your-secret-key-here
FLASK_ENV=production
```

## Local Development

1. Install PostgreSQL locally or use Docker:
```bash
docker run --name postgres -e POSTGRES_PASSWORD=password -p 5432:5432 -d postgres
```

2. Create database:
```bash
createdb posifine
```

3. Set environment variable:
```bash
export DATABASE_URL=postgresql://postgres:password@localhost:5432/posifine
```

## Database Schema

The database will be automatically initialized with tables:
- users
- products  
- sales
- expenses
- activities
- settings