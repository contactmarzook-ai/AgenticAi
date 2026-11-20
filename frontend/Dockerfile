# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
# API_UPSTREAM is substituted into the nginx config at start-up.
ENV API_UPSTREAM=http://api:8000 \
    NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx/conf.d
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
