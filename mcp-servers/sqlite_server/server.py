import asyncio
import sqlite3
from mcp.server.mcpserver.server import MCPServer

mcp = MCPServer("sqlite-mcp-server")


def _get_db():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS demo_users (id INTEGER PRIMARY KEY, name TEXT, role TEXT)")
    cursor.execute("INSERT OR IGNORE INTO demo_users VALUES (1, 'Alice', 'Engineer'), (2, 'Bob', 'Designer')")
    conn.commit()
    return conn


@mcp.tool()
async def read_query(query: str) -> str:
    """
    执行只读 SQL 查询并返回格式化结果

    :param query: 要执行的 SQL SELECT 查询语句
    """
    if not query.strip().upper().startswith("SELECT"):
        return "安全限制：仅允许执行 SELECT 只读查询。"
    try:
        conn = _get_db()
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        return f"查询结果 ({len(rows)} 行):\n{str(rows)}"
    except Exception as e:
        return f"SQL 执行错误: {str(e)}"


@mcp.tool()
async def list_tables() -> str:
    """
    列出 SQLite 数据库中所有的表名
    """
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    return f"数据库表列表: {', '.join(tables)}"


async def main():
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
