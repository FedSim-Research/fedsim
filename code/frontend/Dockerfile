FROM node:20-bookworm

WORKDIR /app

RUN npm install -g npm@11.6.4

COPY package*.json /app/
RUN npm ci

COPY . /app

EXPOSE 4200

CMD ["npm", "run", "start", "--", "--host", "0.0.0.0", "--port", "4200", "--poll", "2000"]
