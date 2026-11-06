FROM node:26.13.0-trixie-slim@sha256:5adad64f9a1fca2d51972caa65983634c8a774eb300d72b20f7f2a0f60368072 AS build

WORKDIR /app
COPY frontend/package*.json ./
RUN npm install --global "$(node --print "require('./package.json').packageManager")" \
    && npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

FROM nginx:1.31.8-alpine@sha256:713fc2ebfd92e8217db451477182ee91944b123d2b1ee9fd5a8c6e91ca6c3a11

COPY deploy/frontend.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/fedsim/browser /usr/share/nginx/html
COPY --from=build /app/dist/fedsim/3rdpartylicenses.txt /usr/share/nginx/html/3rdpartylicenses.txt
COPY LICENSE /usr/share/nginx/html/LICENSE
COPY THIRD_PARTY_NOTICES.md /usr/share/nginx/html/THIRD_PARTY_NOTICES.md

EXPOSE 4200
