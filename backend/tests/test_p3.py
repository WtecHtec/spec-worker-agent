import asyncio
import json
import httpx

BASE_URL = "http://localhost:8000"


async def main():
    print("========================================")
    print("       P3 生产准入与限流日志 自动化测试       ")
    print("========================================")

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. 测试 Liveness & Readiness 探针
        print("\n─── 1. 测试探针接口 (Liveness & Readiness) ───")
        resp = await client.get("/health")
        assert resp.status_code == 200
        print(f"✅ Liveness 探针 (/health): {resp.json()}")

        resp_ready = await client.get("/health/ready")
        assert resp_ready.status_code == 200
        data_ready = resp_ready.json()
        print(f"✅ Readiness 探针 (/health/ready): status={data_ready['status']}")
        print(f"   Database: {data_ready['database']}, Redis: {data_ready['redis']}")
        print(f"   Queue stats: {data_ready['queue']}")
        assert data_ready["database"] == "ok"
        assert data_ready["redis"] == "ok"

        # 2. 测试 Request-ID 中间件与响应头
        print("\n─── 2. 测试 Request-ID 追踪与耗时头 ───")
        resp = await client.get("/health")
        req_id = resp.headers.get("X-Request-ID")
        proc_time = resp.headers.get("X-Process-Time")
        assert req_id is not None, "未找到 X-Request-ID 头"
        assert proc_time is not None, "未找到 X-Process-Time 头"
        print(f"✅ 捕获 X-Request-ID: {req_id}")
        print(f"✅ 捕获 X-Process-Time: {proc_time}")

        # 3. 测试统一错误响应格式
        print("\n─── 3. 测试全局异常处理器统一错误响应格式 ───")
        # 故意发起一个不存在的资源
        resp_err = await client.get("/sessions/non-existent-id/messages", headers={"Authorization": "Bearer invalid"})
        err_json = resp_err.json()
        print(f"👉 统一错误响应结构: {json.dumps(err_json, ensure_ascii=False)}")
        assert "code" in err_json, "缺少统一错误码字段 code"
        assert "message" in err_json, "缺少统一错误消息字段 message"
        assert "request_id" in err_json, "缺少追踪字段 request_id"
        print("✅ 统一错误响应结构验证通过（含 code, message, request_id）")

        # 4. 测试限流头信息 (Rate Limiter)
        print("\n─── 4. 测试 API 限流头 (Rate Limiter Headers) ───")
        # 用户登录
        login_resp = await client.post("/auth/register", json={"email": "p3_test@example.com", "password": "pass1234", "display_name": "P3用户"})
        if login_resp.status_code != 201:
            login_resp = await client.post("/auth/login", json={"email": "p3_test@example.com", "password": "pass1234"})
        token = login_resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        resp_limit = await client.get("/sessions", headers=auth_headers)
        rate_limit = resp_limit.headers.get("X-RateLimit-Limit")
        rate_remaining = resp_limit.headers.get("X-RateLimit-Remaining")
        print(f"✅ RateLimit Limit: {rate_limit}")
        print(f"✅ RateLimit Remaining: {rate_remaining}")
        assert rate_limit is not None, "缺少 X-RateLimit-Limit"

        # 5. 测试用户并发任务配额限制 (User Concurrency Quota)
        print("\n─── 5. 测试单用户全局最大并发任务数配额限制 (Max 3) ───")
        # 创建 4 个会话
        sessions = []
        for i in range(4):
            r = await client.post("/sessions", json={"title": f"配额测试会话-{i+1}"}, headers=auth_headers)
            sessions.append(r.json()["id"])

        print(f"👉 创建了 4 个不同会话: {len(sessions)}")

        # 在前 3 个会话分别启动一个长时间任务（不会冲突单会话限制，但会触发用户全局并发限制）
        tasks = []
        for i in range(3):
            r = await client.post(f"/sessions/{sessions[i]}/messages", json={"content": "处理大文件数据分析"}, headers=auth_headers)
            assert r.status_code == 201
            tasks.append(r.json()["task_id"])
            print(f"   [Task {i+1}] 启动成功: {tasks[-1]}")

        # 尝试启动第 4 个任务（此时已有 3 个 RUNNING 任务）
        r_exceed = await client.post(f"/sessions/{sessions[3]}/messages", json={"content": "第4个并发任务"}, headers=auth_headers)
        print(f"👉 第 4 个任务响应码: {r_exceed.status_code}, 内容: {r_exceed.text}")
        assert r_exceed.status_code == 429, "未能拦截超过并发配额的任务！"
        exceed_json = r_exceed.json()
        assert "quota exceeded" in exceed_json["message"].lower() or "limit" in exceed_json["message"].lower()
        print("✅ 成功拦截超出单用户并发配额的任务 (429 Quota Exceeded)！")

        print("\n🎉 P3 所有生产准入功能（健康探针、结构化日志追踪、统一错误格式、Redis限流、并发配额）全部测试通过！")


if __name__ == "__main__":
    asyncio.run(main())
