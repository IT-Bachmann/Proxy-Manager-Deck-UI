FROM python:3.13-slim
RUN pip install --no-cache-dir cryptography certbot certbot-dns-cloudflare certbot-dns-digitalocean certbot-dns-route53
RUN apt-get update && apt-get install -y --no-install-recommends curl openssl ca-certificates \
    && curl -fsSL https://github.com/acmesh-official/acme.sh/archive/refs/tags/3.1.2.tar.gz | tar -xz -C /opt \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY server.py ./
COPY public ./public
RUN useradd -r -u 10001 proxydeck && mkdir -p /data /generated /var/www/acme /updates && chown -R proxydeck:proxydeck /app /data /generated /var/www/acme /updates
ENV PORT=3000 PROXYDECK_DATA=/data PROXYDECK_CONFIG=/generated PROXYDECK_ACME_WEBROOT=/var/www/acme
EXPOSE 3000
CMD ["python", "server.py"]
