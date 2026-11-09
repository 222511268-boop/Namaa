FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# The API base used by the /api rewrite is fixed at build time.
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
RUN addgroup -S namaa && adduser -S namaa -G namaa
COPY --from=build --chown=namaa:namaa /app/public ./public
COPY --from=build --chown=namaa:namaa /app/.next/standalone ./
COPY --from=build --chown=namaa:namaa /app/.next/static ./.next/static
USER namaa
EXPOSE 3000
CMD ["node", "server.js"]
