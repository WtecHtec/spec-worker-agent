import asyncio
import json
import httpx

BASE_URL = "http://localhost:8000"


async def main():
    import time
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        print("─── 1. 用户登录 / 注册 ───")
        email = f"p1_{int(time.time())}@example.com"
        resp = await client.post("/auth/register", json={"email": email, "password": "pass1234", "display_name": "P1测试"})
        if resp.status_code != 201:
            resp = await client.post("/auth/login", json={"email": "demo@example.com", "password": "demo1234"})
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✅ 登录成功，获取 Token")

        print("\n─── 2. 创建测试会话 ───")
        resp = await client.post("/sessions", json={"title": "P1综合测试会话"}, headers=headers)
        session_id = resp.json()["id"]
        print(f"✅ 会话创建成功: {session_id}")

        print("\n─── 3. 测试 HITL 完整流（暂停 -> 查待办 -> 响应 -> 断点继续 -> 完成） ───")
        resp = await client.post(f"/sessions/{session_id}/messages", json={"content": "请帮我处理上传的文件数据"}, headers=headers)
        hitl_task_id = resp.json()["task_id"]
        print(f"✅ 任务已创建: {hitl_task_id}，等待执行至 HITL 步骤...")

        # 等待任务进入 WAITING_HUMAN
        hitl_req = None
        for _ in range(15):
            await asyncio.sleep(1)
            resp = await client.get(f"/tasks/{hitl_task_id}/hitl/pending", headers=headers)
            if resp.status_code == 200 and resp.json():
                hitl_req = resp.json()
                break

        assert hitl_req is not None, "未在预期时间内检测到 HITL 请求！"
        print(f"✅ 成功捕获 HITL 请求: id={hitl_req['id']}, question={hitl_req['question']}")
        print(f"   选项: {json.dumps(hitl_req['options'], ensure_ascii=False)}")

        # 检查会话消息状态为 WAITING_HUMAN
        resp = await client.get(f"/sessions/{session_id}/messages", headers=headers)
        msgs = resp.json()
        print(f"✅ 会话当前消息状态: {msgs[-1]['content'].get('task_status')}")

        # 用户响应 HITL
        print("👉 用户提交 HITL 响应: 选择 'skip' (跳过异常行)...")
        resp = await client.post(
            f"/tasks/{hitl_task_id}/hitl/{hitl_req['id']}/respond",
            json={"decision": "skip"},
            headers=headers
        )
        assert resp.status_code == 200, f"HITL 响应失败: {resp.text}"
        print(f"✅ HITL 响应成功: {resp.json()}")

        # 等待后续步骤完成
        print("⏳ 等待 Worker 断点续传执行剩余步骤...")
        for _ in range(10):
            await asyncio.sleep(1)
            resp = await client.get(f"/tasks/{hitl_task_id}", headers=headers)
            if resp.json()["status"] == "COMPLETED":
                break

        assert resp.json()["status"] == "COMPLETED", "任务未能顺利完成！"
        print(f"✅ HITL 任务断点续传执行完毕: status=COMPLETED, result={json.dumps(resp.json()['result'], ensure_ascii=False)}")

        print("\n─── 4. 测试并发防重保护（409 Conflict） ───")
        resp1 = await client.post(f"/sessions/{session_id}/messages", json={"content": "销售数据分析任务"}, headers=headers)
        running_task_id = resp1.json()["task_id"]
        print(f"✅ 任务 1 正在运行: {running_task_id}")

        # 在任务 1 还在运行的时候立即发送第二条消息
        resp2 = await client.post(f"/sessions/{session_id}/messages", json={"content": "另一个并发请求"}, headers=headers)
        print(f"👉 并发请求返回码: {resp2.status_code}, 提示: {resp2.json().get('detail')}")
        assert resp2.status_code == 409, "未能拦截会话并发请求！"
        print("✅ 成功拦截同一会话并发冲突 (409 Conflict)！")

        print("\n─── 5. 测试任务取消接口 (DELETE /tasks/{id}) ───")
        print(f"👉 取消进行中的任务: {running_task_id}...")
        resp = await client.delete(f"/tasks/{running_task_id}", headers=headers)
        print(f"✅ 任务取消结果: status={resp.json()['status']}")
        assert resp.json()["status"] == "CANCELLED"

        # 检查取消后会话是否允许发送新消息
        await asyncio.sleep(1)
        resp3 = await client.post(f"/sessions/{session_id}/messages", json={"content": "销售分析第二轮"}, headers=headers)
        assert resp3.status_code == 201, "取消后未能成功发送新任务！"
        new_task_id = resp3.json()["task_id"]
        print(f"✅ 取消后成功开启新一轮任务: {new_task_id}")

        # 等待新任务完成
        print("⏳ 等待新任务执行完成...")
        for _ in range(15):
            await asyncio.sleep(1)
            resp = await client.get(f"/tasks/{new_task_id}", headers=headers)
            if resp.json()["status"] == "COMPLETED":
                break

        print(f"✅ 新任务完成: status={resp.json()['status']}")

        print("\n─── 6. 测试多轮会话消息列表聚合 ───")
        resp = await client.get(f"/sessions/{session_id}/messages", headers=headers)
        all_msgs = resp.json()
        print(f"✅ 会话共包含 {len(all_msgs)} 条消息（完整轮次历史记录）:")
        for idx, m in enumerate(all_msgs):
            print(f"   [{idx+1}] role={m['role']} seq={m['seq']} status={m['status']} content={m['content'].get('text', '')[:40]}")

        print("\n🎉 P1 所有功能全部测试通过！")


if __name__ == "__main__":
    asyncio.run(main())
