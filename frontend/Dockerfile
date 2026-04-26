# Stage 1 — Build the React app
FROM node:18-alpine AS builder

WORKDIR /app

COPY package*.json ./

# Install all deps (including dev) needed for build
RUN npm install

COPY . .

# Build production bundle
RUN npm run build

# Stage 2 — Serve with Nginx
FROM nginx:alpine

# Copy built files into Nginx's serve directory
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy our custom Nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]