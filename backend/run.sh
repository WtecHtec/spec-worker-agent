#!/bin/bash

# 1. 定义你的目标端口
PORT=8000 

# 2. 检查端口是否被占用，如果有，无情强杀
echo "Checking port $PORT..."
PID=$(lsof -t -i:$PORT)

if [ ! -z "$PID" ]; then
    echo "Port $PORT is occupied by PID $PID. Killing it..."
    kill -9 $PID
    echo "Killed successfully."
else
    echo "Port $PORT is free."
fi

# 3. 启动你的后端服务 (替换为你原本启动后端的命令，比如 uvicorn)
echo "Starting backend service..."

uv run python -m uvicorn api_main:app --reload --host 0.0.0.0 --port $PORT