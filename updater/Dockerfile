FROM alpine:3.22
RUN apk add --no-cache git docker-cli docker-cli-compose
COPY update.sh /usr/local/bin/proxydeck-update
RUN chmod 755 /usr/local/bin/proxydeck-update
CMD ["/usr/local/bin/proxydeck-update"]
