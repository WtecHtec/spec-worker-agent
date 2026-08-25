# ─── Stage 1: Build Go Daemon Binary ───
FROM golang:1.22-alpine AS builder

WORKDIR /build

COPY go.mod ./
RUN go mod download || true

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /build/sandbox-daemon ./cmd/daemon/main.go

# ─── Stage 2: Runtime Sandbox Environment ───
FROM python:3.11-slim

# 安装常用基础开发与测试工具、Chromium 浏览器与中文字体支持
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    git \
    procps \
    ca-certificates \
    chromium \
    fonts-noto-cjk \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libasound2 \
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
