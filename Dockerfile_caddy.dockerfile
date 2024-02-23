
#caddy builder (xcaddy) to make caddy build including cloudflare ext.
FROM caddy:latest-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

#pull regular caddy docker image, replace the caddy bins with the just built custom one
FROM caddy:latest as customcaddy
COPY --from=builder /usr/bin/caddy /usr/bin/caddy