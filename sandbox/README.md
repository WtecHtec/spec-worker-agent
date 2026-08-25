# Agent Sandbox (Go Daemon + Docker 隔离执行环境)

基于 Go 编写的极简守护进程与独立容器化沙箱环境，为 LLM Agent 提供安全的代码执行、命令运行与文件读写。

## 特性
* **极致轻量**：Go 静态编译，内存占用 ~10MB，毫秒级就绪。
* **安全隔离**：强行将所有文件读写和 Shell 命令限制在 `/workspace` 内部，杜绝路径穿越攻击。
* **作业控制**：支持设置超时（默认 60s），支持通过 `/exec/kill` 强杀子孙进程树。
* **大输出防护**：命令输出超长（>4000 字符）自动截断保护。

## 快速独立运行

```bash
# 方式 1：Docker Compose 一键启动
docker compose up --build -d

# 方式 2：Docker 镜像独立构建运行
docker build -t agent-sandbox:latest .
docker run -d -p 5000:5000 --name agent_sandbox agent-sandbox:latest
```

## API 接口

| 接口 | 方法 | 说明 | 示例入参 |
|---|---|---|---|
| `/health` | GET | 探针检查 | 无 |
| `/exec` | POST | 执行 Bash 命令 | `{"command": "python3 -c 'print(1+1)'", "timeout": 60}` |
| `/exec/kill` | POST | 强杀执行进程 | `{"exec_id": "exec_12345"}` |
| `/fs/read` | POST | 读取文件 | `{"file_path": "main.py", "start_line": 1, "end_line": 50}` |
| `/fs/write` | POST | 写入文件 | `{"file_path": "main.py", "content": "..."}` |
| `/fs/list` | POST | 列出目录 | `{"dir_path": "."}` |
