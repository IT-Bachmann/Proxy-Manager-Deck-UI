FROM nginx:1.27-alpine
RUN apk add --no-cache inotify-tools
COPY nginx.conf /etc/nginx/nginx.conf
COPY start.sh /usr/local/bin/proxydeck-gateway
RUN chmod +x /usr/local/bin/proxydeck-gateway
CMD ["/usr/local/bin/proxydeck-gateway"]
