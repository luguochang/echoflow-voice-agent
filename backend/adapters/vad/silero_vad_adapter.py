import asyncio
from typing import Dict, Any, Type

import numpy as np
import torch

from backend.core.models.exceptions import ModuleInitializationError, ModuleProcessingError
from backend.core.interfaces.base_vad import BaseVAD
from backend.utils.logging_setup import logger
from backend.utils.paths import resolve_project_path


class SileroVADAdapter(BaseVAD):
    """Silero VAD 语音活动检测适配器

    使用 Silero VAD 模型进行语音活动检测。
    """

    # 默认配置常量
    DEFAULT_MODEL_REPO = "outputs/models/vad/silero-vad"
    DEFAULT_MODEL_NAME = "silero_vad"
    DEFAULT_DEVICE = "cpu"
    DEFAULT_WINDOW_SIZE_16K = 512
    DEFAULT_WINDOW_SIZE_8K = 256

    def __init__(
        self,
        module_id: str,
        config: Dict[str, Any],
    ) -> None:
        super().__init__(module_id, config)

        # 读取 Silero VAD 特定配置
        self.model_repo_path: str = self.config.get("model_repo_path", self.DEFAULT_MODEL_REPO)
        self.model_name: str = self.config.get("model_name", self.DEFAULT_MODEL_NAME)
        self.device: str = self.config.get("device", self.DEFAULT_DEVICE)
        self.force_reload: bool = self.config.get("force_reload_model", False)

        # 错误处理配置
        self.consecutive_failures: int = 0
        self.max_consecutive_failures: int = self.config.get("max_consecutive_failures", 10)

        # 根据采样率确定窗口大小
        default_window: int = (
            self.DEFAULT_WINDOW_SIZE_16K
            if self.sample_rate == 16000
            else self.DEFAULT_WINDOW_SIZE_8K
        )
        self.window_size_samples: int = self.config.get("window_size_samples", default_window)

        self.model: torch.nn.Module | None = None

        logger.info(f"VAD/Silero [{self.module_id}] 配置加载完成:")
        logger.info(f"  - model_repo: {self.model_repo_path}")
        logger.info(f"  - threshold: {self.threshold}")
        logger.info(f"  - sample_rate: {self.sample_rate}")
        logger.info(f"  - device: {self.device}")

    async def _setup_impl(self) -> None:
        """初始化 Silero VAD 模型 (内部实现)"""
        logger.info(f"VAD/Silero [{self.module_id}] 正在初始化模型...")

        try:
            # 判断是本地路径还是 GitHub
            repo_path = resolve_project_path(self.model_repo_path)
            is_local = repo_path.exists() and repo_path.is_dir()

            if is_local:
                source_type = "local"
            elif _looks_like_github_repo(self.model_repo_path):
                source_type = "github"
            else:
                raise ModuleInitializationError(
                    f"模型仓库目录不存在: {repo_path}。请先运行 backend/scripts/download_models.py "
                    "或将 model_repo_path 设置为有效的 GitHub 仓库名，例如 snakers4/silero-vad。"
                )

            # 如果是本地路径，使用绝对路径字符串
            model_source = str(repo_path) if is_local else self.model_repo_path

            logger.info(f"VAD/Silero [{self.module_id}] 从 {source_type} 加载模型: {model_source}")

            # 在线程池中加载模型
            loaded_entity = await asyncio.to_thread(
                torch.hub.load,
                repo_or_dir=model_source,
                model=self.model_name,
                source=source_type,
                force_reload=self.force_reload,
                trust_repo=True if is_local else None
            )

            # 处理返回值（可能是 tuple）
            if isinstance(loaded_entity, tuple) and len(loaded_entity) >= 1:
                self.model = loaded_entity[0]
            else:
                self.model = loaded_entity

            if self.model is None:
                raise ModuleInitializationError("torch.hub.load 返回 None")

            # 设置设备和评估模式
            self.model.to(self.device)
            self.model.eval()

            logger.info(f"VAD/Silero [{self.module_id}] 模型初始化成功")

        except Exception as e:
            logger.error(f"VAD/Silero [{self.module_id}] 初始化失败: {e}", exc_info=True)
            raise ModuleInitializationError(f"Silero VAD 初始化失败: {e}") from e

    async def detect(self, audio_data: bytes) -> bool:
        """检测音频中是否包含语音"""
        if not self.model:
            raise ModuleProcessingError("模型未初始化")

        if not audio_data:
            logger.debug(f"VAD/Silero [{self.module_id}] 音频数据为空")
            return False

        try:
            # 转换音频数据
            audio_int16 = np.frombuffer(audio_data, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            audio_tensor = torch.from_numpy(audio_float32).to(self.device)

            # 处理维度
            if audio_tensor.ndim == 2 and audio_tensor.shape[0] == 1:
                audio_tensor = audio_tensor.squeeze(0)
            elif audio_tensor.ndim != 1:
                logger.error(f"VAD/Silero [{self.module_id}] 音频张量形状错误: {audio_tensor.shape}")
                return False

            expected_size = self.window_size_samples
            total_samples = audio_tensor.shape[-1]
            max_speech_prob = 0.0
            is_speech = False

            # Silero VAD 要求固定窗口。浏览器通常发送 4096 帧的大块音频，
            # 所以这里逐窗扫描，避免只检查开头静音而漏掉后面的语音。
            with torch.no_grad():
                for start in range(0, total_samples, expected_size):
                    if total_samples == expected_size:
                        window = audio_tensor
                    else:
                        window = audio_tensor[start:start + expected_size]

                    if window.shape[-1] < expected_size:
                        padding = expected_size - window.shape[-1]
                        window = torch.nn.functional.pad(window, (0, padding), "constant", 0)

                    speech_prob_tensor = self.model(window, self.sample_rate)
                    speech_prob = speech_prob_tensor.item()
                    max_speech_prob = max(max_speech_prob, speech_prob)

                    if speech_prob >= self.threshold:
                        is_speech = True
                        break

            logger.debug(
                f"VAD/Silero [{self.module_id}] 检测结果: "
                f"is_speech={is_speech}, max_prob={max_speech_prob:.4f}, threshold={self.threshold}"
            )

            # 成功执行，重置失败计数
            self.consecutive_failures = 0

            return is_speech

        except Exception as e:
            self.consecutive_failures += 1
            logger.error(
                f"VAD/Silero [{self.module_id}] 检测失败 ({self.consecutive_failures}/{self.max_consecutive_failures}): {e}",
                exc_info=True
            )

            if self.consecutive_failures >= self.max_consecutive_failures:
                logger.critical(f"VAD/Silero [{self.module_id}] 连续失败次数过多，抛出异常")
                raise ModuleProcessingError(f"Silero VAD 连续失败 {self.consecutive_failures} 次: {e}") from e

            return False

    async def reset_state(self) -> None:
        """重置 VAD 内部状态"""
        if self.model and hasattr(self.model, "reset_states"):
            self.model.reset_states()
            logger.debug(f"VAD/Silero [{self.module_id}] 模型状态已重置")
        await super().reset_state()

    async def _close_impl(self) -> None:
        """关闭模型，释放资源"""
        logger.info(f"VAD/Silero [{self.module_id}] 正在关闭...")

        if self.model:
            del self.model
            self.model = None

        # 清理 CUDA 缓存
        if self.device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()

        logger.info(f"VAD/Silero [{self.module_id}] 已关闭")


def load() -> Type["SileroVADAdapter"]:
    """加载 SileroVAD 适配器类"""
    return SileroVADAdapter


def _looks_like_github_repo(value: str) -> bool:
    """Return True for torch.hub repo strings like owner/repo or owner/repo:ref."""
    if value.startswith(("/", ".", "~")):
        return False
    repo_part = value.split(":", 1)[0]
    return repo_part.count("/") == 1
