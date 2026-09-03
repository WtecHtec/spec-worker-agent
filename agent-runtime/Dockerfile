FROM python:3.11-slim

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# 复制依赖配置
COPY pyproject.toml ./

# 使用 uv 安装依赖（不含项目本身，提升层缓存命中率）
RUN uv sync --no-install-project --no-dev

# 复制源码与配置文件
COPY . .

# 同步安装项目本身
RUN uv sync --no-dev

# 环境变量默认值
ENV HOST=0.0.0.0
ENV PORT=8123
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8123

# 使用 uv run 启动 langgraph dev（原生热重载，无浏览器）
CMD ["uv", "run", "langgraph", "dev", "--host", "0.0.0.0", "--port", "8123", "--no-browser"]