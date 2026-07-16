# syntax=docker/dockerfile:1
# D2=B: the frontend is a separate compose service (nginx), not static files
# baked into the application image.

FROM node:22-slim AS build

WORKDIR /app

# Copy the dependency manifest and install first, before any source, so source
# edits do not invalidate the (slow) install layer — same layering rule the
# application image follows.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
