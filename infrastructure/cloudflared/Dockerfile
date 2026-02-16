FROM alpine:3.19

ARG TARGETARCH

RUN apk add --no-cache ca-certificates curl \
  && case "${TARGETARCH}" in \
    amd64) CLOUD_FLARED_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" ;; \
    arm64) CLOUD_FLARED_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64" ;; \
    arm) CLOUD_FLARED_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm" ;; \
    *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
  esac \
  && curl -fsSL "${CLOUD_FLARED_URL}" -o /usr/local/bin/cloudflared \
  && chmod +x /usr/local/bin/cloudflared \
  && cloudflared --version

ENTRYPOINT ["cloudflared"]