FROM node:20-alpine AS deps

WORKDIR /app
COPY frontend/package*.json /app/
RUN npm install

FROM node:20-alpine AS builder

WORKDIR /app
COPY --from=deps /app/node_modules /app/node_modules
COPY frontend /app
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000

COPY --from=builder /app/.next /app/.next
COPY --from=builder /app/public /app/public
COPY --from=builder /app/package*.json /app/
COPY --from=deps /app/node_modules /app/node_modules

EXPOSE 3000

CMD ["sh", "-c", "npm run start -- -H 0.0.0.0 -p ${PORT:-3000}"]
