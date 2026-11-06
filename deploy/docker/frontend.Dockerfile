FROM node:22-bookworm AS build

WORKDIR /app

RUN npm install -g npm@11.6.4

COPY frontend/package*.json /app/
RUN npm ci --no-audit --no-fund

COPY frontend/ /app/
RUN npm run build

FROM nginx:1.27-alpine

COPY deploy/frontend.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/fedsim/browser /usr/share/nginx/html
COPY --from=build /app/dist/fedsim/3rdpartylicenses.txt /usr/share/nginx/html/3rdpartylicenses.txt
COPY LICENSE /usr/share/nginx/html/LICENSE
COPY THIRD_PARTY_NOTICES.md /usr/share/nginx/html/THIRD_PARTY_NOTICES.md

EXPOSE 4200
