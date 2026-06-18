# Stage 1: Build do OHIF
FROM node:24-alpine AS builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app
COPY . .

RUN pnpm install --frozen-lockfile
RUN cd platform/app && PUBLIC_URL=/viewer/ APP_CONFIG=config/default.js pnpm build

# Stage 2: Nginx servindo o build
FROM nginx:alpine AS ohif

ARG LEX_PACS_VERSION=0.4.0
LABEL org.lex-pacs.version="${LEX_PACS_VERSION}"

COPY --from=builder /app/platform/app/dist /usr/share/nginx/html
COPY nginx/ohif-static.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
