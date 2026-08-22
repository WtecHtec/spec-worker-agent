"""
人机协同 (HITL) 领域服务（校验审批状态与决策合法性）
"""
from typing import Optional
from src.domain.entities.models import HitlRequest
from src.domain.exceptions import HitlAlreadyResolvedException, HitlExpiredException


class HitlDecisionService:
    @staticmethod
    def validate_and_apply(
        hitl_request: HitlRequest,
        decision: str,
        user_input: Optional[dict] = None,
    ) -> None:
        """校验审批单有效性并应用决策"""
        if not hitl_request.is_pending():
            raise HitlAlreadyResolvedException(hitl_request.id, hitl_request.status)

        if hitl_request.is_expired():
            raise HitlExpiredException(hitl_request.id)

        hitl_request.resolve(decision, user_input)
