FROM node:22-slim AS build
WORKDIR /app
# npm workspaces: root manifest + member manifests, then install all deps
COPY package.json package-lock.json* ./
COPY frontend/package.json frontend/package.json
COPY packages/platform/web/package.json packages/platform/web/package.json
RUN npm install
COPY frontend ./frontend
COPY packages ./packages
COPY apps ./apps
COPY backend/openapi.json ./backend/openapi.json
RUN npx openapi-typescript ./backend/openapi.json -o frontend/src/api/schema.d.ts
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build --workspace frontend

FROM node:22-slim
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/frontend/dist ./dist
EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
