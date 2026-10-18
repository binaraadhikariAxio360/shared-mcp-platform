FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3004

# PORT env var is set by docker-compose (PORT=3004)
# -H 0.0.0.0 is required so the container is reachable from outside
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0", "-p", "3004"]