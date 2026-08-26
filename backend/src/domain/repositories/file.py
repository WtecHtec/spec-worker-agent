from abc import ABC, abstractmethod
from typing import Optional
from src.domain.entities.models import SessionFile


class IFileRepository(ABC):
    """会话文件数据仓储接口"""

    @abstractmethod
    async def upsert(
        self,
        session_id: str,
        user_id: str,
        file_path: str,
        file_name: str,
        file_size: int,
        mime_type: str,
        category: str,
        storage_type: str = "sandbox",
        task_id: Optional[str] = None,
        storage_key: Optional[str] = None,
    ) -> SessionFile:
        """创建或根据 (session_id, file_path) 覆盖更新文件记录"""
        ...

    @abstractmethod
    async def list_by_session(
        self,
        session_id: str,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SessionFile], int]:
        """查询指定会话的文件列表（返回列表及总数）"""
        ...

    @abstractmethod
    async def get_by_id(self, file_id: str) -> Optional[SessionFile]:
        """根据文件 ID 查询单个文件信息"""
        ...

    @abstractmethod
    async def get_by_path(self, session_id: str, file_path: str) -> Optional[SessionFile]:
        """根据 session_id 与 file_path 查询单个文件"""
        ...

    @abstractmethod
    async def delete_by_id(self, file_id: str) -> bool:
        """标记删除或物理删除文件"""
        ...


class IFileVersionRepository(ABC):
    """文件版本数据仓储接口"""

    @abstractmethod
    async def create(
        self,
        file_id: str,
        session_id: str,
        version_num: int,
        file_size: int,
        task_id: Optional[str] = None,
        diff_content: Optional[str] = None,
        storage_key: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> "FileVersion":
        """创建新的文件版本记录"""
        ...

    @abstractmethod
    async def list_by_file_id(self, file_id: str) -> list["FileVersion"]:
        """查询指定文件的所有版本记录（降序）"""
        ...

    @abstractmethod
    async def get_by_id(self, version_id: str) -> Optional["FileVersion"]:
        """获取单个版本详情"""
        ...

    @abstractmethod
    async def get_latest_version(self, file_id: str) -> Optional["FileVersion"]:
        """获取指定文件的最新版本"""
        ...
