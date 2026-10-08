"""Chinese error projections for the Zhizhi Agent transport."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from gewu_agent_runtime import ConversationMessage
from gewu_agent_runtime.domain import MessageKind
from zhizhi import MessagePage

_ERROR_MESSAGES_ZH = {
    "": "任务执行状态已失效，请重新发送。",
    "runtime_capacity": "智能助手服务繁忙，请稍后重试。",
    "concurrent_run": "当前会话已有任务正在执行，请稍后再试。",
    "conversation_not_active": "当前会话不存在或已不可用。",
    "cancelled": "本次回答已停止。",
    "run_lease_lost": "任务执行状态已失效，请重新发送。",
    "model_not_configured": "当前范围未配置可用模型。",
    "model_authentication_failed": "模型服务认证失败，请联系管理员检查模型配置。",
    "model_permission_denied": "当前模型配置无权访问所选模型，请联系管理员。",
    "model_rate_limited": "模型服务请求过于频繁，请稍后重试。",
    "model_timeout": "模型服务响应超时，请稍后重试。",
    "model_unavailable": "模型服务暂时不可用，请稍后重试。",
    "model_request_rejected": "模型服务拒绝了本次请求，请稍后重试或调整问题。",
    "vision_unsupported": "当前模型不支持图片输入。",
    "image_capacity_exceeded": "图片处理任务繁忙，请稍后重试。",
    "skill_capacity_exceeded": "可用技能内容过多，暂时无法执行本次请求。",
    "context_compaction_failed": "对话上下文整理失败，请稍后重试或发起新会话。",
    "context_limit_exceeded": "对话内容过长，请发起新会话后重试。",
    "message_write_conflict": "消息写入冲突，请勿重复提交并稍后重试。",
    "empty_response": "模型未返回有效内容，请重新尝试。",
    "iteration_limit": "本次任务执行步骤过多，已自动停止。",
    "agent_internal_error": "服务内部异常，请稍后重试。",
    "agent_unavailable": "智能助手服务暂时不可用，请稍后重试。",
    "runtime_error": "智能助手执行失败，请稍后重试。",
}
_UNKNOWN_ERROR_MESSAGE_ZH = "智能助手执行失败，请稍后重试。"


def localized_error_message(code: str, message: str, *, error_id: str = "") -> str:
    """Return a stable Chinese message while preserving a safe support reference."""

    localized = _ERROR_MESSAGES_ZH.get(code)
    if localized is None:
        localized = (
            message
            if any("\u4e00" <= character <= "\u9fff" for character in message)
            else _UNKNOWN_ERROR_MESSAGE_ZH
        )
    if error_id:
        return f"{localized} 参考编号：{error_id}"
    return localized


def localized_message_page(page: MessagePage) -> MessagePage:
    """Localize persisted Runtime errors and restore UTC awareness of stored timestamps."""

    return page.model_copy(
        update={"messages": tuple(_localized_history_message(message) for message in page.messages)}
    )


def _localized_history_message(message: ConversationMessage) -> ConversationMessage:
    update: dict[str, Any] = {"created_at": _utc(message.created_at)}
    if message.kind is not MessageKind.ERROR:
        return message.model_copy(update=update)
    code = str(message.payload.get("code") or "")
    error_id = str(message.payload.get("error_id") or "")
    content = localized_error_message(code, message.content, error_id=error_id)
    update["content"] = content
    update["payload"] = {**message.payload, "error": content}
    return message.model_copy(update=update)


def _utc(value: datetime) -> datetime:
    """MySQL DATETIME readback is naive UTC; tag it so the wire format carries the Z suffix."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
