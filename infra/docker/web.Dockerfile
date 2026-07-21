FROM node:22-bookworm-slim

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /workspace

COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci

COPY apps/web ./apps/web
COPY contracts ./contracts

CMD ["npm", "run", "dev", "--workspace", "@brand-studio/web", "--", "--hostname", "0.0.0.0"]
