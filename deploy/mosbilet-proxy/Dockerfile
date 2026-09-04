FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends squid-openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY squid.conf /etc/squid/squid.conf
USER proxy
CMD ["squid", "-N", "-f", "/etc/squid/squid.conf"]
