# Multi-stage: build once with the toolchain, ship a static binary on a
# distroless-style base. The BINARY arg lets all three Go services share one
# Dockerfile rather than maintaining three near-identical copies.
FROM golang:1.22-alpine AS build
ARG BINARY
WORKDIR /src

# Dependency layer cached separately from source, so a code change does not
# re-download the module graph.
COPY go/go.mod go/go.sum ./
RUN go mod download

COPY go/ ./
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/service ./cmd/${BINARY}

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget && adduser -D -u 10001 hm
COPY --from=build /out/service /usr/local/bin/service
USER hm
ENTRYPOINT ["/usr/local/bin/service"]
