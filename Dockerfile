# syntax=docker/dockerfile:1
FROM node:lts-alpine AS base
WORKDIR /app
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./
RUN npm install --production=false || true
COPY . .
RUN npx prisma generate
RUN npm run build

FROM node:lts-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=base /app/package.json ./
COPY --from=base /app/node_modules ./node_modules
COPY --from=base /app/dist ./dist
COPY --from=base /app/prisma ./prisma
COPY --from=base /app/.env.example ./
EXPOSE 8080
CMD ["node", "dist/server.js"]
