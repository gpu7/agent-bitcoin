# Loop image with lndclient PayInvoice fix for LND >=0.17/0.18:
# SendPaymentV2 requires timeout_seconds; stock lndclient omits it → L402 auth fails.
#
# Build (on AWS or any Docker host):
#   docker build -t agent-bitcoin/loop:v0.34.0-beta-timeoutfix \
#     -f docker/loop-timeout-fix/Dockerfile docker/loop-timeout-fix
#
# Use:
#   LOOPD_IMAGE=agent-bitcoin/loop:v0.34.0-beta-timeoutfix ./wire-loopd.sh mainnet --recreate

ARG LOOP_TAG=v0.34.0-beta
ARG LNDCLIENT_REF=v0.21.0-2
ARG GO_IMAGE=golang:1.25-bookworm

FROM ${GO_IMAGE} AS builder
ARG LOOP_TAG
ARG LNDCLIENT_REF

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 --branch "${LOOP_TAG}" https://github.com/lightninglabs/loop.git .
RUN git clone --depth 1 --branch "${LNDCLIENT_REF}" https://github.com/lightninglabs/lndclient.git /lndclient

# Ensure router SendPaymentV2 always gets a non-zero timeout (LND hard requirement).
COPY patch-lndclient-payinvoice-timeout.sh /tmp/patch-lndclient-payinvoice-timeout.sh
RUN chmod +x /tmp/patch-lndclient-payinvoice-timeout.sh \
  && /tmp/patch-lndclient-payinvoice-timeout.sh /lndclient/router_client.go

RUN go mod edit -replace github.com/lightninglabs/lndclient=/lndclient \
  && go mod tidy \
  && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/loopd ./cmd/loopd \
  && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/loop ./cmd/loop

FROM lightninglabs/loop:${LOOP_TAG}
COPY --from=builder /out/loopd /bin/loopd
COPY --from=builder /out/loop /bin/loop
