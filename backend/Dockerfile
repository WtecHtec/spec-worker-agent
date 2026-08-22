FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装基础依赖与 uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 复制依赖定义文件
COPY pyproject.toml .

# 安装 Python 依赖
RUN uv sync --frozen || uv sync

# 复制后端源代码与配置
COPY . .

# 暴露 API 端口
EXPOSE 8000

# 默认启动 API 服务 (可在 docker-compose 中按服务覆盖 command)
CMD ["uv", "run", "uvicorn", "api_main:app", "--host", "0.0.0.0", "--port", "8000"]
