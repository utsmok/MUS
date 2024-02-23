FROM python:3.12.2-alpine as base
RUN set -xe \
    && mkdir -p /usr/web/app /var/www/mus/static

WORKDIR /usr/web/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

#caddy builder (xcaddy) to make caddy build including cloudflare ext.
FROM caddy:latest-builder AS builder
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare
#pull regular caddy docker image, replace the caddy bins with the just built custom one
FROM caddy:latest as customcaddy
COPY --from=builder /usr/bin/caddy /usr/bin/caddy


