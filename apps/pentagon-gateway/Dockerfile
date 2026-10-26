FROM node:24-alpine
WORKDIR /app
COPY --chown=node:node src ./src
COPY package.json ./
USER node
CMD ["node", "src/server.mjs"]
