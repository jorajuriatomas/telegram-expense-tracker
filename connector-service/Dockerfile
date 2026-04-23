# syntax=docker/dockerfile:1.7

# ---- build stage ----
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json ./
COPY src ./src

RUN npx tsc -p tsconfig.json

# ---- runtime stage ----
FROM node:20-alpine AS runtime

ENV NODE_ENV=production

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=build /app/dist ./dist

EXPOSE 3000

CMD ["node", "dist/src/server.js"]
