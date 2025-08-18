# frontend/Dockerfile - OPTIMIZED FOR DEVELOPMENT
# Built for proper permissions without requiring sudo

FROM node:20-alpine AS base

# Set environment variables
ENV NODE_ENV=development \
    NUXT_HOST=0.0.0.0 \
    NUXT_PORT=3000 \
    HOME=/app

# Create app directory
WORKDIR /app

# Install development tools for debugging
RUN apk add --no-cache \
    curl \
    iputils \
    net-tools \
    tcpdump \
    bind-tools \
    busybox-extras \
    netcat-openbsd \
    bash

########################
# DEVELOPMENT TARGET - Optimized for local development
########################
FROM base AS development

# Copy package files first (for better caching)
COPY package*.json ./

# Install dependencies including dev dependencies
RUN npm install && \
    npm cache clean --force && \
    npm install -g cross-env

# Create required directories and ensure they're writable
RUN mkdir -p .nuxt .output node_modules && \
    chmod -R 777 /app /app/.nuxt /app/.output /app/node_modules

# Create a simplified entrypoint script that doesn't need sudo
COPY --chmod=755 ./scripts/dev-entrypoint.sh /app/scripts/dev-entrypoint.sh

# Default development command
CMD ["/app/scripts/dev-entrypoint.sh"]

########################
# BUILD TARGET - For building the Nuxt application
########################
FROM base AS builder

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source files
COPY . .

# Build Nuxt
RUN npm run build

########################
# PRODUCTION TARGET - Minimal and secure
########################
FROM base AS production-image
ENV NODE_ENV=production

# Copy package files and install production dependencies only
COPY package*.json ./
RUN npm ci --only=production

# Copy only built app from previous stage
COPY --from=builder /app/.output /app/.output
COPY --from=builder /app/public /app/public

# Start command for production
CMD ["node", ".output/server/index.mjs"]
