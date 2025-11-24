# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files (build context is repo root, Dockerfile is in frontend/)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install

# Copy source code (build context is repo root, Dockerfile is in frontend/)
COPY frontend/ .

# Build the application (use VITE_API_URL if provided, otherwise default)
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration (build context is repo root, Dockerfile is in frontend/)
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy startup script (build context is repo root, Dockerfile is in frontend/)
COPY frontend/start-nginx.sh /start-nginx.sh
RUN chmod +x /start-nginx.sh

# Expose port (Railway will set PORT env var, default to 80)
EXPOSE 80

# Use startup script to inject environment variables
CMD ["/start-nginx.sh"]


