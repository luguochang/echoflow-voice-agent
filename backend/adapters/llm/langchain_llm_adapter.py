"""LangChain LLM 适配器

使用统一的三个参数配置：
- model: 模型名称（自动检测 provider）
- api_key: API 密钥
- base_url: API 端点（可选）

通过 langchain 的 init_chat_model 自动选择正确的客户端。
"""

import asyncio
import json
import os
from typing import Any, AsyncGenerator, Type

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from backend.core.interfaces.base_llm import BaseLLM
from backend.core.models import TextData
from backend.core.models.exceptions import ModuleInitializationError, ModuleProcessingError
from backend.utils.logging_setup import logger


class LangChainLLMAdapter(BaseLLM):
    """LangChain LLM 适配器

    使用三个核心参数配置 LLM，init_chat_model 自动选择客户端：
    - model_name / model_name_env_var: 模型名称，可由环境变量覆盖
    - api_key / api_key_env_var: 统一的 API 密钥（环境变量名默认 API_KEY）
    - base_url: API 端点（可选，用于自定义端点）

    配置示例:
        # 最简配置（自动检测 provider）
        model_name: "claude-sonnet-4-20250514"
        api_key_env_var: "API_KEY"  # 或直接 api_key: "sk-xxx"

        # 自定义端点（如 OpenRouter）
        model_name: "anthropic/claude-3-opus"
        api_key_env_var: "API_KEY"
        base_url: "https://openrouter.ai/api/v1"
    """

    MAX_HISTORY_LENGTH = 20
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(self, module_id: str, config: dict[str, Any]) -> None:
        super().__init__(module_id, config)

        # 统一三要素
        self.model_name = self._resolve_model_name()
        self.api_key: str = self._resolve_api_key()
        self.base_url: str | None = self._resolve_base_url()

        # 历史管理配置
        self.max_history_length: int = config.get("max_history_length", self.MAX_HISTORY_LENGTH)
        self.max_retries: int = config.get("max_retries", self.MAX_RETRIES)
        self.retry_delay: float = config.get("retry_delay", self.RETRY_DELAY)
        self.raw_openai_compatible: bool = bool(config.get("raw_openai_compatible", False))
        self.request_timeout: float = float(config.get("request_timeout", 60.0))

        # 运行时状态
        self.chat_histories: dict[str, list[BaseMessage]] = {}
        self.llm: BaseChatModel | None = None

        logger.info(f"LLM [{self.module_id}] 配置:")
        logger.info(f"  - model: {self.model_name}")
        logger.info(f"  - base_url: {self.base_url or 'auto'}")
        logger.info(f"  - temperature: {self.temperature}")
        logger.info(f"  - raw_openai_compatible: {self.raw_openai_compatible}")

    def _resolve_api_key(self) -> str:
        """解析 API Key

        优先级: 环境变量 > 配置文件
        默认环境变量名: API_KEY
        """
        # 从指定环境变量读取
        api_key_env = self.config.get("api_key_env_var", "API_KEY")
        if env_value := os.getenv(api_key_env):
            logger.debug(f"LLM [{self.module_id}] 从环境变量 '{api_key_env}' 读取 API Key")
            return env_value

        # 从配置读取
        if config_key := self.config.get("api_key"):
            return config_key

        raise ModuleInitializationError(
            f"缺少 API Key，请设置环境变量 '{api_key_env}' 或在配置中提供 'api_key'"
        )

    def _resolve_model_name(self) -> str:
        """Resolve model name from an optional environment variable."""
        if model_name_env := self.config.get("model_name_env_var"):
            if env_value := os.getenv(model_name_env):
                return env_value
        return self.model_name

    def _resolve_base_url(self) -> str | None:
        """解析 Base URL"""
        if base_url_env := self.config.get("base_url_env_var"):
            if env_value := os.getenv(base_url_env):
                return env_value
        return self.config.get("base_url")

    def _init_model(self) -> BaseChatModel:
        """初始化 LLM 模型

        使用 init_chat_model 自动选择正确的客户端。
        """
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "api_key": self.api_key,
            "temperature": self.temperature,
        }

        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens

        if self.base_url:
            kwargs["base_url"] = self.base_url

        # 使用 init_chat_model 自动选择
        try:
            from langchain.chat_models import init_chat_model

            return init_chat_model(**kwargs)
        except ImportError:
            logger.warning("init_chat_model 不可用，使用手动选择")
        except Exception as e:
            logger.debug(f"init_chat_model 失败: {e}，尝试手动选择")

        # 手动选择 fallback
        return self._init_model_fallback()

    def _init_model_fallback(self) -> BaseChatModel:
        """手动选择模型客户端（fallback）"""
        kwargs: dict[str, Any] = {
            "temperature": self.temperature,
        }
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens

        model_lower = self.model_name.lower()

        # 有 base_url 或包含 "/" 的模型名 → OpenAI 兼容模式
        if self.base_url or "/" in self.model_name:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key,
                base_url=self.base_url,
                **kwargs,
            )

        # Claude 模型 → Anthropic
        if model_lower.startswith("claude"):
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=self.model_name,
                api_key=self.api_key,
                **kwargs,
            )

        # 默认 OpenAI
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            **kwargs,
        )

    async def _setup_impl(self) -> None:
        """初始化 LLM"""
        logger.info(f"LLM [{self.module_id}] 正在初始化...")

        try:
            if self.raw_openai_compatible:
                logger.info(f"LLM [{self.module_id}] 使用 OpenAI-compatible raw HTTP 模式")
                return

            self.llm = self._init_model()
            logger.info(f"LLM [{self.module_id}] 初始化成功")
        except Exception as e:
            logger.error(f"LLM [{self.module_id}] 初始化失败: {e}", exc_info=True)
            raise ModuleInitializationError(f"LLM 初始化失败: {e}") from e

    async def chat_stream(
        self,
        text: TextData,
        session_id: str,
    ) -> AsyncGenerator[TextData, None]:
        """流式对话生成"""
        if not text.text or not text.text.strip():
            yield TextData(text="", chunk_id=session_id, is_final=True)
            return

        if self.raw_openai_compatible:
            async for chunk in self._chat_stream_raw_openai_compatible(text, session_id):
                yield chunk
            return

        if not self.llm:
            raise ModuleProcessingError("LLM 未初始化")

        try:
            # 初始化会话历史
            if session_id not in self.chat_histories:
                self.chat_histories[session_id] = [SystemMessage(content=self.system_prompt)]

            self.chat_histories[session_id].append(HumanMessage(content=text.text))
            self._trim_history(session_id)

            # 流式生成（带重试）
            full_response = ""
            for retry in range(self.max_retries + 1):
                try:
                    async for chunk in self.llm.astream(self.chat_histories[session_id]):
                        if hasattr(chunk, "content") and chunk.content:
                            full_response += chunk.content
                            yield TextData(
                                text=chunk.content,
                                chunk_id=session_id,
                                is_final=False,
                            )
                    break
                except Exception as e:
                    if retry < self.max_retries:
                        logger.warning(f"LLM [{self.module_id}] 重试 {retry + 1}/{self.max_retries}: {e}")
                        await asyncio.sleep(self.retry_delay * (retry + 1))
                    else:
                        raise ModuleProcessingError(f"生成失败: {e}") from e

            self.chat_histories[session_id].append(AIMessage(content=full_response))
            yield TextData(text="", chunk_id=session_id, is_final=True)

        except ModuleProcessingError:
            raise
        except Exception as e:
            logger.error(f"LLM [{self.module_id}] 生成失败: {e}", exc_info=True)
            raise ModuleProcessingError(f"生成失败: {e}") from e

    def _trim_history(self, session_id: str) -> None:
        """修剪会话历史"""
        history = self.chat_histories[session_id]
        if len(history) <= self.max_history_length:
            return

        system_msg = history[0] if isinstance(history[0], SystemMessage) else SystemMessage(content=self.system_prompt)
        recent = history[-(self.max_history_length - 1):]
        self.chat_histories[session_id] = [system_msg] + recent

    async def _chat_stream_raw_openai_compatible(
        self,
        text: TextData,
        session_id: str,
    ) -> AsyncGenerator[TextData, None]:
        """通过裸 HTTP 调用 OpenAI-compatible Chat Completions 流式接口。"""
        had_history = session_id in self.chat_histories
        previous_history = list(self.chat_histories.get(session_id, []))

        if session_id not in self.chat_histories:
            self.chat_histories[session_id] = [SystemMessage(content=self.system_prompt)]

        self.chat_histories[session_id].append(HumanMessage(content=text.text))
        self._trim_history(session_id)

        full_response = ""
        emitted_content = False
        for retry in range(self.max_retries + 1):
            try:
                async for content in self._iter_raw_openai_compatible_chunks(session_id):
                    if content and content.strip():
                        full_response += content
                        emitted_content = True
                        yield TextData(
                            text=content,
                            chunk_id=session_id,
                            is_final=False,
                        )
                break
            except Exception as e:
                if emitted_content:
                    self._restore_history(session_id, had_history, previous_history)
                    raise ModuleProcessingError(f"生成失败: {e}") from e
                if retry < self.max_retries:
                    logger.warning(f"LLM [{self.module_id}] raw 重试 {retry + 1}/{self.max_retries}: {e}")
                    await asyncio.sleep(self.retry_delay * (retry + 1))
                else:
                    self._restore_history(session_id, had_history, previous_history)
                    raise ModuleProcessingError(f"生成失败: {e}") from e

        self.chat_histories[session_id].append(AIMessage(content=full_response))
        yield TextData(text="", chunk_id=session_id, is_final=True)

    async def _iter_raw_openai_compatible_chunks(
        self,
        session_id: str,
    ) -> AsyncGenerator[str, None]:
        """迭代 OpenAI-compatible SSE 文本增量。"""
        url = self._chat_completions_url()
        payload = self._raw_openai_compatible_payload(session_id)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.request_timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                saw_sse_data = False
                saw_content = False
                non_sse_lines: list[str] = []

                async for line in response.aiter_lines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith(":"):
                        continue
                    if not stripped.startswith("data:"):
                        non_sse_lines.append(stripped)
                        continue

                    saw_sse_data = True
                    content, done = self._parse_openai_compatible_sse_line(line)
                    if content:
                        saw_content = True
                        yield content
                    if done:
                        break

                if not saw_sse_data:
                    content = self._parse_openai_compatible_json_response("\n".join(non_sse_lines))
                    if content:
                        yield content
                        return
                    raise ModuleProcessingError("LLM 响应为空")

                if not saw_content:
                    raise ModuleProcessingError("LLM 响应为空")

    def _restore_history(
        self,
        session_id: str,
        had_history: bool,
        previous_history: list[BaseMessage],
    ) -> None:
        """恢复 raw 请求前的会话历史。"""
        if had_history:
            self.chat_histories[session_id] = previous_history
        else:
            self.chat_histories.pop(session_id, None)

    def _chat_completions_url(self) -> str:
        """获取 Chat Completions endpoint。"""
        base_url = (self.base_url or "https://api.openai.com/v1").rstrip("/")
        return f"{base_url}/chat/completions"

    def _raw_openai_compatible_payload(self, session_id: str) -> dict[str, Any]:
        """构造 OpenAI-compatible Chat Completions 请求体。"""
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                self._message_to_openai_compatible(message)
                for message in self.chat_histories[session_id]
            ],
            "stream": True,
        }

        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            payload["temperature"] = self.temperature

        return payload

    def _message_to_openai_compatible(self, message: BaseMessage) -> dict[str, Any]:
        """将 LangChain message 转为 Chat Completions message。"""
        if isinstance(message, SystemMessage):
            role = "system"
        elif isinstance(message, AIMessage):
            role = "assistant"
        elif isinstance(message, HumanMessage):
            role = "user"
        else:
            role = "user"

        return {
            "role": role,
            "content": message.content,
        }

    def _parse_openai_compatible_json_response(self, body: str) -> str:
        """解析非 SSE 的 OpenAI-compatible JSON 响应。"""
        body = body.strip()
        if not body:
            raise ModuleProcessingError("LLM 响应为空")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as e:
            preview = body[:200]
            raise ModuleProcessingError(f"无法解析非 SSE 响应: {preview}") from e

        if "error" in payload:
            error = payload["error"]
            if isinstance(error, dict):
                message = error.get("message") or error.get("type") or str(error)
            else:
                message = str(error)
            raise ModuleProcessingError(message)

        choices = payload.get("choices") or []
        if not choices:
            raise ModuleProcessingError("LLM 响应缺少 choices")

        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content")
        if content is None:
            delta = choice.get("delta") or {}
            content = delta.get("content")

        if not content:
            raise ModuleProcessingError("LLM 响应为空")

        return content

    def _parse_openai_compatible_sse_line(self, line: str) -> tuple[str, bool]:
        """解析 OpenAI-compatible SSE 行，返回 (content, done)。"""
        line = line.strip()
        if not line or line.startswith(":"):
            return "", False
        if not line.startswith("data:"):
            return "", False

        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            return "", True

        payload = json.loads(data)
        if "error" in payload:
            error = payload["error"]
            if isinstance(error, dict):
                message = error.get("message") or error.get("type") or str(error)
            else:
                message = str(error)
            raise ModuleProcessingError(message)

        choices = payload.get("choices") or []
        if not choices:
            return "", False

        choice = choices[0]
        delta = choice.get("delta") or {}
        content = delta.get("content")

        if content is None:
            message = choice.get("message") or {}
            content = message.get("content")

        return content or "", False

    def clear_history(self, session_id: str) -> None:
        """清除会话历史"""
        self.chat_histories.pop(session_id, None)

    def get_history_length(self, session_id: str) -> int:
        """获取会话历史长度"""
        return len(self.chat_histories.get(session_id, []))

    async def _close_impl(self) -> None:
        """关闭 LLM"""
        self.chat_histories.clear()
        self.llm = None


def load() -> Type[LangChainLLMAdapter]:
    """加载适配器类"""
    return LangChainLLMAdapter
