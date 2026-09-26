# Airframe frontend: React + TypeScript + Vite dashboard, run via npm (dev server with
# hot reload). This image is self-contained - it never needs anything from the backend
# folder at build time; at runtime it proxies /api/* to the backend service (see
# ../docker-compose.yml, which points VITE_BACKEND_URL at the backend container).
#
#   docker build -t airframe-frontend .
#   docker run --rm -p 5173:5173 -e VITE_BACKEND_URL=http://host.docker.internal:8000 airframe-frontend

FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# --host so Vite binds 0.0.0.0 inside the container, not just localhost.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
