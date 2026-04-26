FROM node:18

WORKDIR /app

COPY package.json ./
RUN NODE_ENV=development npm install && \
    npm install @rollup/rollup-linux-arm64-gnu --save-optional

COPY . .

EXPOSE 8080

CMD ["npx", "--yes", "vite", "--host", "0.0.0.0"]