# EchoFlow Voice Agent 本地运行说明

本文档记录在 macOS 本机把项目拉下并运行时的实际步骤、已验证结果和当前阻塞点。

## 结论

- 后端是 Python 项目，根目录有 `pyproject.toml` 和 `uv.lock`，并且 `.python-version` 指定 `3.13`。建议用 `uv` 运行，不建议按 README 里的旧命令 `pip install -r requirements.txt`，因为仓库没有 `requirements.txt`。
- 本机原本没有全局 `uv`。我已在项目内用 `.cache/uv-bootstrap` bootstrap 了一个本地 `uv`，不污染全局环境。
- 基础后端和测试环境已跑通。本次新增 raw OpenAI-compatible LLM 路径、VAD 大音频块检测、ASR 前端显示路径、PCM 音频转换和启动参数覆盖后，相关单测已覆盖。
- 最小 WebSocket 后端已跑通，监听验证地址为 `ws://127.0.0.1:18765`。
- Silero VAD 仓库地址已确认没错：`snakers4/silero-vad`。本机 `git clone` 偶发超时，但 GitHub zip 归档可下载，下载脚本已增加 zip fallback。
- 浏览器版前端可用静态服务器启动，地址是 `http://127.0.0.1:5173/`；它会连接 `ws://localhost:8765`。
- Tauri 桌面端还不能启动，因为本机没有 `cargo`。`npm ci` 已成功，`npm run dev` 失败在 `cargo metadata`。

## 问题记录 / 后续优化清单

### 已修复

- 仓库没有 `requirements.txt`，README 旧命令 `pip install -r requirements.txt` 不可用。当前文档已改为 `uv sync --extra full --extra dev`。
- 原始依赖锁和 Python 3.13 不匹配，FunASR 相关依赖链会拉到不兼容的旧 `llvmlite`。已更新 `uv.lock`。
- `backend/utils/audio_converter.py` 依赖 `scipy`，但基础依赖里缺失。已加入 `pyproject.toml`。
- 原代码缺少 `backend/core/models/config_data.py`，导致部分状态/配置相关测试和导入失败。已补齐。
- `backend/main.py` 原本不稳定加载项目根目录 `.env`，导致 API key/base URL 容易配了但没生效。已补 `.env` 加载。
- `--host`/`--port` 原本只写环境变量，没有覆盖 WebSocket 配置。现在会在配置加载后应用并校验端口范围。
- LLM 配置原本不能通过环境变量覆盖 OpenAI-compatible `base_url`。已支持 `base_url_env_var`。
- LLM 模型名现在支持通过 `MODEL_NAME` 环境变量覆盖，OpenRouter 和中转站不需要修改 YAML。
- 某些中转站裸 `/chat/completions` 可用，但 LangChain/OpenAI SDK 流式调用不稳定。已增加 `raw_openai_compatible: true` 路径，直接用 `httpx` 调 OpenAI-compatible SSE。
- ASR 默认模型路径和实际 ModelScope 下载目录不一致。已把配置对齐到 `outputs/models/asr/SenseVoiceSmall/models/iic--SenseVoiceSmall/snapshots/master`。
- Silero VAD 的 GitHub 仓库地址是对的，但本机 `git clone` 容易超时。下载脚本已增加 GitHub zip fallback。
- VAD 之前只检查音频块第一窗 `512` 个采样，浏览器每次发约 `4096` 帧时可能漏判后半段语音。已改成逐窗扫描。
- 音频 ASR 成功后，后端之前只内部触发 LLM，没有发前端监听的 `ASR_UPDATE`。已补前端 ASR 文本事件。
- TTS 模式下回复刚好以标点结束时，后端之前可能不发送文本结束标记。已补空文本 `SERVER_TEXT_RESPONSE` 且 `is_final=true`。
- 测试里有硬编码路径，换机器后容易失败。已改为按项目根目录解析。

### 已绕过 / 当前限制

- Tauri 桌面端需要 Rust/Cargo。macOS 可以安装，不是 mac 不能跑；只是当前机器还没有 Rust 工具链，所以 `npm run dev` 失败在 `cargo metadata`。
- 现在完整功能先用浏览器静态页面跑通，前端地址 `http://127.0.0.1:5173/`，后端 WebSocket `127.0.0.1:8765`。
- 完整语音后端启动较慢。SenseVoice 模型约 900MB，加载后 Python 进程内存常见在 1.6GB 左右，首次启动可能在 `初始化模块 'asr'...` 停几十秒。
- EdgeTTS 依赖外部网络。初始化阶段是弱检查，启动不因连接失败中断，但首次真实 TTS 请求仍可能受网络影响。

### 待优化

- 前端麦克风按钮现在是“按住说话”：`mousedown` 开始录音，`mouseup`/`mouseleave` 停止录音。普通点一下会录到极短音频，后端基本没有可识别内容，所以用户会感觉“点了没用”。建议改成更直观的“点击开始录音，再点击结束录音”，并在录音中显示明确状态。
- 前端 WebSocket 地址硬编码为 `ws://localhost:8765`。建议改成可配置，或者根据当前页面 host 自动生成。
- README 应补齐完整运行路径：uv、Python 版本、模型下载、`.env`、OpenAI-compatible 配置、浏览器版启动、Tauri/Rust 前置依赖。
- README 应明确区分三种启动模式：最小 WebSocket、浏览器文本模式、完整语音模式。
- 完整语音配置建议保留 `backend/configs/full_server.openai_compatible.yaml.example`，避免每次手写临时 YAML。
- 前端录音失败时只显示 `Microphone access denied`，信息太粗。建议区分浏览器不支持、权限拒绝、非安全上下文、WebSocket 未连接、录音时间过短。
- 语音按钮应禁用或提示连接状态：WebSocket 未连接时不应让用户以为可以录音。
- README 和命令行入口需要保持项目名、仓库 URL、启动命令一致，避免用户按旧名称操作。

## 目录位置

```bash
cd /path/to/echoflow-voice-agent
```

## 安装 uv

### 方案 A：项目内 bootstrap，已验证

如果机器没有全局 `uv`，可以在项目内安装一个只给本项目用的 `uv`：

```bash
python3 -m venv .cache/uv-bootstrap
.cache/uv-bootstrap/bin/python -m pip install --upgrade pip uv
.cache/uv-bootstrap/bin/uv --version
```

后续命令可直接使用：

```bash
.cache/uv-bootstrap/bin/uv <command>
```

本机验证版本：

```text
uv 0.11.28
```

### 方案 B：全局安装

也可以按 uv 官方文档安装全局命令：<https://docs.astral.sh/uv/getting-started/installation/>

macOS/Linux 官方安装命令是：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

如果已经有 `pipx`，官方也支持：

```bash
pipx install uv
```

## Python 依赖

完整开发环境：

```bash
.cache/uv-bootstrap/bin/uv sync --extra full --extra dev
```

说明：

- `uv` 会按 `.python-version` 自动使用/安装 CPython 3.13。
- 原始 `uv.lock` 里的 `funasr -> umap-learn -> pynndescent -> llvmlite==0.36.0` 和 Python 3.13 冲突。已更新锁文件，把 FunASR 相关依赖升级到支持 Python 3.13 的版本。
- `backend/utils/audio_converter.py` 顶层依赖 `scipy`，所以已把 `scipy` 加入基础依赖。

如果只想跑基础单元测试，不加载 ASR/VAD/TTS 模型，也可以：

```bash
.cache/uv-bootstrap/bin/uv sync --extra dev
```

## 后端最小启动，已验证

这个配置只验证 WebSocket 服务能启动，不加载 ASR/VAD/TTS 模型，也不会验证真实 LLM 调用。

```bash
.cache/uv-bootstrap/bin/uv run python -m backend.main server \
  --config backend/configs/minimal_server.yaml.example
```

启动成功时应看到：

```text
[Server] Ready and waiting for client connections...
Protocol/WebSocket [protocols] 服务器已启动
```

本机已验证监听：

```text
ws://127.0.0.1:18765
```

如果默认 `8765` 被占用，可以直接覆盖端口：

```bash
.cache/uv-bootstrap/bin/uv run python -m backend.main server \
  --config backend/configs/minimal_server.yaml.example \
  --port 18765
```

## 浏览器前端文本模式，已验证

如果只想先看前端聊天效果，不想加载 ASR/VAD/TTS 语音模型，可以用这个轻量配置：

```bash
API_KEY=你的真实 API Key \
BASE_URL=https://openrouter.ai/api/v1 \
MODEL_NAME=openai/gpt-4.1-mini \
.cache/uv-bootstrap/bin/uv run python -m backend.main server \
  --config backend/configs/text_server.openai_compatible.yaml.example
```

默认模型写在：

```yaml
backend/configs/text_server.openai_compatible.yaml.example
modules:
  llm:
    config:
      default:
        model_name: "openai/gpt-4.1-mini"
        model_name_env_var: "MODEL_NAME"
        raw_openai_compatible: true
```

使用中转站时设置 `BASE_URL` 和 `MODEL_NAME`，不需要修改 YAML。

然后启动前端静态页面：

```bash
cd frontend/src
python3 -m http.server 5173 --bind 127.0.0.1
```

浏览器打开：

```text
http://127.0.0.1:5173/
```

前端代码里的 WebSocket 地址是 `ws://localhost:8765`，所以这个文本模式配置的后端端口也固定为 `8765`。

## 完整语音后端启动

完整语音配置会加载 ASR、LLM、TTS、VAD。

如果使用 OpenAI-compatible 中转站或 OpenRouter raw 模式，建议用这个完整语音示例配置：

```bash
API_KEY=你的真实 API Key \
BASE_URL=https://openrouter.ai/api/v1 \
MODEL_NAME=openai/gpt-4.1-mini \
.cache/uv-bootstrap/bin/uv run python -m backend.main server \
  --config backend/configs/full_server.openai_compatible.yaml.example
```

然后启动前端静态页面：

```bash
cd frontend/src
python3 -m http.server 5173 --bind 127.0.0.1
```

浏览器打开：

```text
http://127.0.0.1:5173/
```

完整后端启动会比文本模式慢很多。ASR 的 SenseVoice 模型约 900MB，加载后 Python 进程常见内存占用在 1.6GB 左右；首次启动时终端可能会在 `初始化模块 'asr'...` 停几十秒。

本机最终端口 `8765` 已验证完整链路：

```text
REGISTER SYSTEM_SERVER_SESSION_START True
ASR_UPDATE 派放时间早上九点至下午五点
REPLY 派放时间是早上九点至下午五点。
AUDIO_CHUNKS 30
AUDIO_BYTES 21600
TEXT_FINAL True
```

这说明当前完整链路已覆盖：

- 浏览器/客户端音频格式等价输入。
- VAD 检测并触发 ASR。
- ASR 返回 `ASR_UPDATE` 给前端。
- LLM 通过 OpenAI-compatible `/chat/completions` 返回文本。
- EdgeTTS 返回可播放音频块。

## 语音链路说明

语音界面不是单个“语音转文字”功能，而是一条实时链路：

- `WebSocket`：浏览器和后端之间的实时连接。前端麦克风音频、文字输入、停止说话信号都从这里发给后端；后端的 ASR 文本、LLM 回复、TTS 音频也从这里回到前端。
- `VAD`：Voice Activity Detection，语音活动检测。它只判断这一段音频里有没有人在说话，不负责把语音转成文字。本项目用的是 Silero VAD。
- `ASR`：Automatic Speech Recognition，语音转文字。VAD 判断有语音后，后端把缓冲的音频交给 ASR，本项目默认用 FunASR SenseVoice。
- `LLM`：大语言模型。ASR 得到用户文本后，再把文本发给模型生成回复。本项目的 LLM 适配器支持 OpenAI-compatible chat completions，所以可以接 OpenRouter，也可以接兼容 OpenAI 接口的中转站。
- `TTS`：Text To Speech，文字转语音。LLM 回复出来后，后端把文本合成为音频给前端播放。本项目默认用 EdgeTTS。
- `流式链路`：不是等所有步骤完全结束才返回，而是音频块、文本块、语音块分批流动。理想路径是：浏览器音频块 -> VAD 检测 -> ASR 出最终文本 -> LLM 流式出字 -> TTS 分句合成 -> 前端边收边播放。
- `对话打断`：如果机器人正在回复/播报时用户又开始说话，前端清空播放队列，后端标记当前输出被打断，并用新输入开启下一轮对话。
- `适配器架构`：ASR、VAD、LLM、TTS、WebSocket 都不是写死在核心流程里，而是由配置选择具体实现。以后换 OpenRouter、换中转站、换 ASR/TTS，优先改配置和对应 adapter。
- `端到端测试`：不只测某个函数，而是模拟真实客户端，从 WebSocket 发文本或音频，确认后端能返回 `ASR_UPDATE`、`SERVER_TEXT_RESPONSE`、`SERVER_AUDIO_RESPONSE` 这类真实事件。

如果语音界面看不到转文字，优先排查这几项：

- 麦克风按钮当前是“按住说话”，不是点击切换。需要按住按钮说话 1-2 秒以上，然后松开；只点一下通常不会产生有效音频。
- 后端是否用完整语音配置启动。`text_server.openai_compatible.yaml.example` 只加载 LLM 和 WebSocket，不加载 ASR/VAD/TTS，所以麦克风不会真正转文字。
- WebSocket 后端是否在 `127.0.0.1:8765` 监听。前端静态页面默认连接 `ws://localhost:8765`。
- 浏览器是否拿到了麦克风权限。
- 后端日志是否出现 ASR 结果。识别成功时会有类似 `[AudioInput] ASR result` 和 `Final transcript`。

本次已修复三个会影响语音界面显示的问题：

- 前端录音每次会发送约 `4096` 帧音频，后端 VAD 之前只检查第一窗 `512` 个采样。如果第一窗是静音、后面才有语音，会漏判。现在 VAD 会逐窗扫描整个音频块。
- 音频 ASR 成功后，后端之前只把内部 `ASR_RESULT` 用来触发 LLM，没有转成前端监听的 `ASR_UPDATE`。现在音频来源的最终识别文本会先发给前端显示，再继续触发 LLM/TTS。
- TTS 模式下如果模型回复刚好以标点结束，后端之前可能不发送文本结束标记，前端下一轮消息有机会接到上一轮后面。现在会补发空文本 `SERVER_TEXT_RESPONSE` 且 `is_final=true`。

### 1. 配置 API Key

复制环境变量模板：

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
API_KEY=你的真实 API Key
BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=openai/gpt-4.1-mini
```

默认 `backend/configs/config.yaml` 使用 OpenRouter，并从 `API_KEY`、`BASE_URL`、`MODEL_NAME` 读取运行配置。

如果你用的是 OpenAI 兼容中转站，可以这样填：

```bash
API_KEY=中转站给你的 API Key
BASE_URL=https://你的中转站域名/v1
MODEL_NAME=中转站支持的模型名
```

注意两点：

- `API_KEY` 填中转站后台给你的 key，不一定是 OpenAI 官方 key。
- `BASE_URL` 一般要填 OpenAI 兼容接口根地址，通常以 `/v1` 结尾。具体以中转站文档为准。
- `MODEL_NAME` 填服务商模型列表中实际暴露的名称。

已用一个 OpenAI-compatible 中转站做过临时验证：

- `/v1/models` 返回 200。
- 模型列表里有 `gpt-5.5`。
- `/v1/chat/completions` 使用 `gpt-5.5` 可以正常返回。
- 但通过 LangChain/OpenAI Python SDK 流式调用时，本机遇到过 `502/503 Service temporarily unavailable`。

因此项目现在支持一个兼容开关：

```yaml
raw_openai_compatible: true
```

打开后，LLM 适配器会绕开 LangChain/OpenAI Python SDK，直接用裸 `httpx` 请求 OpenAI-compatible `/chat/completions` SSE 流。这个模式适合“裸请求可用，但 SDK 流式请求不稳定”的 OpenAI-compatible 中转站。

最终版本如果想稳定同时接 Claude/OpenAI 一类模型，仍建议优先用 OpenRouter：这个项目当前 LLM 适配器走 OpenAI-compatible chat completions，OpenRouter 正好适合做多模型路由。使用 OpenRouter 时可以先保持默认 LangChain 路径；如果某个 OpenAI-compatible 端点出现 SDK 兼容问题，再开启 `raw_openai_compatible: true`。

如果只想验证初始化流程，也可以临时：

```bash
API_KEY=dummy-for-startup
```

但真实对话请求会因为无效密钥失败。

### 2. 下载模型

```bash
.cache/uv-bootstrap/bin/uv run python backend/scripts/download_models.py
```

本机已成功下载 SenseVoice：

```text
outputs/models/asr/SenseVoiceSmall/models/iic--SenseVoiceSmall/snapshots/master/model.pt
```

默认配置已对齐到这个路径：

```yaml
modules:
  asr:
    config:
      funasr_sensevoice:
        model_dir: "outputs/models/asr/SenseVoiceSmall/models/iic--SenseVoiceSmall/snapshots/master"
```

### 3. 准备 Silero VAD

脚本会先尝试 clone：

```bash
git clone https://github.com/snakers4/silero-vad \
  outputs/models/vad/silero-vad
```

如果 `git clone` GitHub 仓库时超时：

```text
Recv failure: Operation timed out
```

当前脚本会自动 fallback 到 zip 下载。也可以手动执行：

```bash
mkdir -p outputs/models/vad
curl -L -o /tmp/silero-vad.zip \
  https://github.com/snakers4/silero-vad/archive/refs/heads/master.zip
unzip -q /tmp/silero-vad.zip -d /tmp
rm -rf outputs/models/vad/silero-vad
mv /tmp/silero-vad-master outputs/models/vad/silero-vad
```

或者在网络恢复后重新运行：

```bash
.cache/uv-bootstrap/bin/uv run python backend/scripts/download_models.py
```

本机已验证 VAD 本地仓库可加载：

```text
vad_ready True RecursiveScriptModule
```

如果这个目录不存在，默认完整后端会明确报错：

```text
模型仓库目录不存在: outputs/models/vad/silero-vad
```

### 4. 启动完整后端

VAD 仓库和 API Key 都准备好后：

```bash
API_KEY=你的真实 API Key \
BASE_URL=https://你的中转站域名/v1 \
.cache/uv-bootstrap/bin/uv run python -m backend.main server \
  --config backend/configs/full_server.openai_compatible.yaml.example
```

默认监听配置：

```text
127.0.0.1:8765
```

如果端口被占用，改 `backend/configs/full_server.openai_compatible.yaml.example`：

```yaml
modules:
  protocols:
    config:
      websocket:
        port: 18765
```

## 前端 / Tauri 桌面端

Node 依赖已验证：

```bash
cd frontend
npm ci
```

本机结果：

```text
added 3 packages
found 0 vulnerabilities
```

启动桌面端：

```bash
npm run dev
```

当前本机失败：

```text
failed to run 'cargo metadata' command
No such file or directory (os error 2)
```

原因是没有安装 Rust/Cargo。Tauri v2 官方前置条件见：<https://v2.tauri.app/start/prerequisites/>

macOS 桌面开发至少需要：

```bash
xcode-select --install
curl --proto '=https' --tlsv1.2 https://sh.rustup.rs -sSf | sh
```

安装后重新打开终端，并确认：

```bash
cargo --version
```

再运行：

```bash
cd frontend
npm run dev
```

## 已执行验证命令

基础单元测试：

```bash
.cache/uv-bootstrap/bin/uv run pytest backend/tests/unit -q
```

结果：

```text
359 passed, 1 skipped
```

VAD 单元测试：

```bash
.cache/uv-bootstrap/bin/uv run pytest backend/tests/unit/adapters/vad/test_silero_vad_adapter.py -q
```

结果：

```text
15 passed
```

最小后端启动：

```bash
.cache/uv-bootstrap/bin/uv run python -m backend.main server \
  --config backend/configs/minimal_server.yaml.example
```

结果：

```text
Protocol/WebSocket [protocols] 服务器已启动
```

完整默认后端启动：

```bash
API_KEY=dummy-for-startup \
.cache/uv-bootstrap/bin/uv run python -m backend.main server
```

此前目录缺失时的结果：

```text
Silero VAD 初始化失败: 模型仓库目录不存在: outputs/models/vad/silero-vad
```

前端依赖：

```bash
cd frontend
npm ci
```

结果：

```text
found 0 vulnerabilities
```

桌面端：

```bash
cd frontend
npm run dev
```

当前结果：

```text
failed to run 'cargo metadata'
```

## 本次修复/调整

- 补回缺失的 `backend/core/models/config_data.py`，否则后端入口和单元测试都会因 `ModuleNotFoundError` 失败。
- 修正 `.gitignore`，避免 `backend/core/models/` 被 `models/` 规则误忽略。
- 将 `scipy` 加入基础依赖，因为 `audio_converter.py` 直接导入它。
- 更新 `uv.lock` 中 FunASR/Torch/Numba/llvmlite 相关依赖，解决 Python 3.13 下 `llvmlite==0.36.0` 无法安装的问题。
- 修正测试里硬编码的作者本机配置路径。
- 新增 `backend/configs/minimal_server.yaml.example`，用于快速验证 WebSocket 后端启动。
- 新增 `backend/configs/text_server.openai_compatible.yaml.example`，用于浏览器前端文本模式联调。
- LLM 适配器新增 `raw_openai_compatible: true` 模式，绕开 LangChain/OpenAI Python SDK，直接请求 OpenAI-compatible `/chat/completions` SSE 流，解决部分中转站裸请求可用但 SDK 流式调用 `502/503` 的问题。
- Silero VAD 适配器现在会对大音频块逐窗扫描，适配浏览器前端一次发送 `4096` 帧音频的录音方式。
- 音频 ASR 最终结果现在会转发为前端监听的 `ASR_UPDATE`，语音识别成功后页面能显示用户说的话；文本输入仍只按普通聊天消息处理，避免重复显示。
- ASR 前的裸 PCM 音频转换现在直接走 raw PCM/pydub 路径，不再先尝试 torchaudio 文件解码，避免 TorchCodec 缺失时出现误导性的错误日志。
- 对齐 SenseVoice 模型下载后的实际路径。
- 改善 Silero VAD 本地仓库缺失时的错误提示。
- 下载脚本在 Silero clone 失败时会打印 stderr，并自动 fallback 到 GitHub zip 下载。
