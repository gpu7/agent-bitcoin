FROM docker.n8n.io/n8nio/n8n:latest AS base

# Temporary stage to get docker CLI
FROM alpine:3.20 AS docker-cli
RUN apk add --no-cache curl
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz | tar xz --strip-components=1 -C /usr/local/bin docker/docker

# Final image - run as root so docker socket works
FROM base
USER root
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
RUN chmod +x /usr/local/bin/docker

# Optional: create docker group and add node user (if you want to switch back later)
# RUN addgroup -g 999 docker && adduser node docker
