# ─── Stage 1: Build Go Daemon Binary ───
FROM golang:1.22-alpine AS builder

WORKDIR /build

COPY go.mod ./
RUN go mod download || true

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /build/sandbox-daemon ./cmd/daemon/main.go

# ─── Stage 2: Runtime Sandbox Environment ───
FROM python:3.11-slim

# 安装常用基础开发与测试工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    git \
    procps \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# 从编译阶段拷贝 Daemon 单二进制文件
COPY --from=builder /build/sandbox-daemon /usr/local/bin/sandbox-daemon
RUN chmod +x /usr/local/bin/sandbox-daemon

ENV SANDBOX_PORT=5050
ENV SANDBOX_WORKSPACE=/workspace

EXPOSE 5050

# 启动 Sandbox Daemon
CMD ["sandbox-daemon"]
