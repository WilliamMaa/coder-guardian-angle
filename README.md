# Repo Semantic Memory & Engineering Guard

> 一个给 AI coder 使用的项目语义记忆层——从入口函数消化代码，沉淀调用链语义，持续刷新项目理解，让不同 coder session 共享同一份稳定上下文，并基于这份语义记忆做结构、测试、老代码和实验守卫。

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [安装](#安装)
- [快速开始](#快速开始)
- [核心概念](#核心概念)
- [CLI 命令参考](#cli-命令参考)
- [配置](#配置)
- [数据模型](#数据模型)
- [开发说明](#开发说明)

---

## 它解决什么问题

在真实项目里使用 AI coder 时，反复遇到五类痛点：

1. **每次从零理解项目** —— 每个新 session 都要重新读代码、重新建立上下文，浪费大量 token 和时间。
2. **不同 session 理解不一致** —— 第一个对话说"不要改 credits 服务"，第二个对话根本不知道，直接改了。
3. **新代码结构乱飘** —— AI 为了完成局部需求，把业务逻辑塞进 utils、绕过已有 service、重复实现已有能力。
4. **对老代码缺少敬畏** —— 底层生产资产（如计费核心、鉴权核心）被随意修改，引发连锁故障。
5. **实验异常被错误合理化** —— 长周期实验结果不符合预期时，AI 倾向于强行解释"理论就该差"，而不是排查实现 bug。

**Repo Semantic Memory & Engineering Guard**（简称 `repoctx`）不是 coding agent，也不是 IDE 插件。它是放在 **coder 和项目之间的一层控制层**，把"读代码理解项目"变成一份**可复用、可版本化、可刷新的语义资产**。

---

## 安装

### 环境要求

- Python 3.10+
- Git 2.30+
- 可访问 Tencent MaaS API（`https://tokenhub.tencentmaas.com`）或兼容 OpenAI 协议的端点

### 安装

```bash
git clone <repo-url> repoctx-guard
cd repoctx-guard
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install -e .
```

验证安装：

```bash
repoctx --help
```

---

## 快速开始

### 第一步：初始化项目

进入你的项目根目录，运行：

```bash
cd /path/to/your-project
repoctx init
```

这会创建：
- `.repoctx.yaml` —— 项目标记与配置文件
- `.repograph/` —— 语义记忆存储目录，包含：
  - `semantic_memory/{entries,paths,symbols,flows,context_packs,versions}/`
  - `tasks/` —— 任务工作区
  - `guards/` —— 工程守卫规则
  - `legacy/` —— 老代码保护与复用层
  - `experiments/` —— 实验记忆
  - `reports/` —— 检查报告

你可以自定义项目元数据：

```bash
repoctx init --project-name my-api --language python --framework django
```

### 第二步：配置 API Key

`repoctx` 使用 LLM 生成语义卡片，需要配置 API Key。支持两种方式：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | `.repoctx.yaml` | 目标项目下的 `model_provider.api_key` 字段 |
| 2 | `config.ini` | repoctx 工具根目录下的 `[DEFAULT] tencent_cloud_llm_api_key` |

**方式 A：按项目配置（推荐）**

在目标项目的 `.repoctx.yaml` 中设置：

```yaml
model_provider:
  api_key: "sk-xxxxxxxxxxxxxxxx"
```

**方式 B：全局配置**

在 repoctx 工具根目录创建 `config.ini`：

```ini
[DEFAULT]
tencent_cloud_llm_api_key = sk-xxxxxxxxxxxxxxxx
```

全局配置一次，服务器上所有项目共用。如果某个项目又在 `.repoctx.yaml` 中配置了 key，则优先使用项目本地的 key。

> ⚠️ **安全提醒**：`.repoctx.yaml` 和 `config.ini` 必须加入 `.gitignore`，禁止提交到版本仓库。

### 第三步：消化一个入口函数

```bash
repoctx digest-entry backend/free_call/views.py --only start_free_call --depth 3
```

`digest-entry` 会：
1. **Tracer** 递归追踪 `start_free_call` 的调用链（深度 3）
2. **LLM** 分析源代码和调用关系，生成语义卡片：
   - **EntryCard** —— 入口函数的业务职责和主调用链
   - **SymbolCards** —— 深层函数的语义角色、副作用、复用指导
   - **ContextPack** —— 给 coder 直接读的压缩上下文（流程摘要、关键路径、陷阱提示）
3. **持久化** 到 `.repograph/semantic_memory/`

输出示例：

```
Digest complete: 3 cards generated.
  → /path/to/your-project/.repograph/semantic_memory/entries/entry.backend.free_call.views.start_free_call.yaml
  → /path/to/your-project/.repograph/semantic_memory/symbols/symbol.backend.free_call.services.start_call.yaml
  → /path/to/your-project/.repograph/semantic_memory/context_packs/context.start_free_call.yaml
```

你可以读取生成的 ContextPack，它长这样：

```markdown
# Context Pack: Free Call Flow

## Flow Summary
Free Call starts from the frontend dial action and eventually invokes
the backend call start endpoint. The flow resolves auth/session state,
checks call eligibility, interacts with credit services, creates call
records, invokes the provider, and emits tracking events.

## Main Entrypoints
- `start_free_call`

## Main Start Path
`DialPad.onDialClick` → `useAuthGuard` → `freeCallApi.startCall`
→ `start_free_call` → `free_call.services.start_call`
→ `credits.services.get_available_balance` → `call_provider.start_call`
→ `track_free_call_event`

## Important Deep Functions
- `credits.services.get_available_balance`: public credit read surface.
- `credits.services.consume_credits`: state mutation core, used by multiple flows.

## Known Pitfalls
- Do not duplicate credit balance logic.
- Auth timing changes usually belong near frontend action/auth guard.
```

---

## 核心概念

| 概念 | 说明 |
|------|------|
| **Semantic Card** | 语义资产卡片，描述代码的语义角色而非结构。类型：entry / path / symbol / flow。 |
| **Entry Card** | 描述一个入口函数的业务职责、主调用链、业务角色。 |
| **Symbol Card** | 描述深层函数/服务/模型的项目语义角色、副作用、复用指导。 |
| **Context Pack** | 给 coder 直接读的压缩上下文文档，汇总入口、路径、重要函数、陷阱。 |
| **Call Graph** | 从入口函数递归追踪调用链得到的树状结构。 |
| **Task Workspace** | 单个需求的共享任务理解层，包含 accepted_understanding、change_plan、frozen_assumptions 等。 |

---

## CLI 命令参考

### Semantic Memory（语义记忆）

| 命令 | 状态 | 说明 |
|------|------|------|
| `repoctx init` | ✅ 可用 | 初始化项目，创建 `.repoctx.yaml` 和 `.repograph/` 目录树 |
| `repoctx digest-entry <file>` | ✅ 可用 | 入口语义消化，生成 Entry Card、Symbol Cards、Context Pack |
| `repoctx stale` | ⏳ 待开发 | 检查哪些语义资产已过期 |
| `repoctx refresh --affected` | ⏳ 待开发 | 增量刷新过期 card |
| `repoctx semantic-diff --since main` | ⏳ 待开发 | 总结代码改动带来的业务语义变化 |
| `repoctx export-context <flow>` | ⏳ 待开发 | 导出 context pack 为 markdown |

### Task Workspace（任务工作区）

| 命令 | 状态 | 说明 |
|------|------|------|
| `repoctx task start "name" --entry <file::sym>` | ⏳ 待开发 | 创建任务工作区，冻结理解 |
| `repoctx task export <id>` | ⏳ 待开发 | 导出任务上下文给 coder |
| `repoctx task status <id>` | ⏳ 待开发 | 查看任务状态 |
| `repoctx validate --task <id>` | ⏳ 待开发 | 验证 diff 是否违背任务约束 |

### Guards（工程守卫）

| 命令 | 状态 | 说明 |
|------|------|------|
| `repoctx status` | ⏳ 待开发 | working tree 健康度 |
| `repoctx structure-check` | ⏳ 待开发 | 新代码结构检查 |
| `repoctx test-impact --task <id>` | ⏳ 待开发 | 测试影响分析 |
| `repoctx legacy-check` | ⏳ 待开发 | 老代码保护检查 |
| `repoctx commit-check` | ⏳ 待开发 | commit 前统一 gate |

### Experiment Agent（实验诊断）

| 命令 | 状态 | 说明 |
|------|------|------|
| `repoctx exp init` | ⏳ 待开发 | 初始化实验工作区 |
| `repoctx exp check --config <cfg>` | ⏳ 待开发 | 实验前检查 |
| `repoctx exp run --name <n> --cmd "cmd"` | ⏳ 待开发 | 运行实验 |
| `repoctx exp summarize <run_id>` | ⏳ 待开发 | 实验总结 |
| `repoctx exp diagnose <run_id>` | ⏳ 待开发 | 双轨诊断（同时怀疑理论和实现） |

---

## 配置

`.repoctx.yaml` 示例：

```yaml
project_name: my-project
version: "0.1.0"
language: python
framework: django
scan_paths:
  - "."
exclude_paths:
  - ".git"
  - ".venv"
  - "node_modules"
  - "__pycache__"
  - ".repograph"
modules:
  - name: backend
    path: backend
    type: backend
  - name: frontend
    path: frontend
    type: frontend
model_provider:
  api_key: null
  base_url: "https://tokenhub.tencentmaas.com/v1"
  model: "deepseek-v4-flash-202605"
  timeout: 60
```

`model_provider` 配置兼容 OpenAI 协议，你可以替换为其他端点：

```yaml
model_provider:
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"
```

---

## 数据模型

所有语义资产以 YAML 形式存储在 `.repograph/semantic_memory/` 下，核心字段包括：

```yaml
card_type: entry | path | symbol | flow
id: "entry.free_call.start_free_call"
version:
  code_hash: "sha256 of source file"
  dependency_hash: "sha256 of downstream symbols"
  git_commit: "9f1a2c"
  generated_at: "2026-05-31T12:00:00Z"
  status: fresh | stale | deprecated
```

完整模型定义见 `src/repoctx/cards/models.py`。

---

## 开发说明

### 项目结构

```
repoctx-guard/
├── src/repoctx/
│   ├── cli.py                      # CLI 入口（Click）
│   ├── initialization.py           # repoctx init 逻辑
│   ├── loader.py                   # 配置加载
│   ├── cards/                      # Card 数据模型
│   │   └── models.py
│   ├── llm/                        # LLM 客户端与 Prompt 流水线
│   │   ├── client.py
│   │   ├── pipeline.py
│   │   ├── tokenizer.py
│   │   ├── logger.py
│   │   └── errors.py
│   ├── semantic_memory/            # 语义记忆引擎（Phase 2）
│   │   ├── engine.py               # SemanticDigestEngine
│   │   ├── prompt_builder.py       # Prompt 组装
│   │   └── versioning.py           # Hash / Git 工具
│   ├── tracer/                     # 调用链追踪器（Phase 1）
│   │   ├── base.py
│   │   ├── factory.py
│   │   └── python/                 # Python 专用追踪器
│   │       ├── import_resolver.py
│   │       ├── call_extractor.py
│   │       ├── module_resolver.py
│   │       └── tracer.py
│   ├── models/                     # 配置模型
│   │   └── config.py
│   └── utils/                      # 工具函数
│       ├── yaml_io.py
│       └── project.py
├── tests/                          # 测试套件（pytest）
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

### 运行测试

```bash
# 运行全部测试
pytest

# 运行特定模块
pytest tests/test_tracer.py -v
pytest tests/test_semantic_memory.py -v
pytest tests/test_initialization.py -v

# 运行集成测试（需要配置真实 API Key）
pytest tests/test_llm_client.py -v -k "not test_real_api_call"
```

当前测试状态：**109 passed, 1 skipped**

### 代码规范

```bash
# 静态检查
ruff check src/ tests/

# 类型检查
mypy src/
```

---

## License

MIT
