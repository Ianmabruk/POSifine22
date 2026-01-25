# POS Backend (SQLite local, MySQL central)

Production-grade POS backend using Node.js, Express, Prisma, Zod, JWT/Refresh, Socket.IO. Local-first writes to SQLite with deterministic sync to MySQL.

- Local DB: SQLite (WAL + FULL synchronous) via Prisma
- Central DB: MySQL via Prisma
- Clean Architecture modules
- Offline-first: all writes go to SQLite; SyncQueue triggers background sync

## Dev quickstart

1. cp .env.example .env and set JWT secrets
2. npm install
3. npx prisma generate
4. npx prisma migrate deploy --schema prisma/schema.prisma
5. npm run dev

Health: GET /api/v1/health
