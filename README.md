# RepoCtx Guard

> AI-assisted Development Control Plane — 面向复杂研发项目的 AI 辅助开发控制层。

RepoCtx Guard 不是 coding agent，也不是 IDE 插件。它是站在 AI coder 旁边的工程控制系统，负责约束它、提醒它、审查它、记录它。

**核心目标：** 让 AI coder 在复杂项目和长周期实验中，不要乱改、不要乱飘、不要忘上下文、不要破坏老代码、不要让新代码变成未来屎山。

---

## 目录

- [安装](#安装)
- [配置](#配置)
- [快速开始](#快速开始)
- [CLI 命令参考](#cli-命令参考)
- [工程宪法](#工程宪法)
- [开发说明](#开发说明)

---

## 安装

### 环境要求

- Python 3.10+
- Git 2.30+
- 网络环境可访问 `https://tokenhub.tencentmaas.com`

### 1. 克隆仓库并进入项目目录

```bash
git clone <repo-url> repoctx-guard
cd repoctx-guard
```

### 2. 创建并激活 Python 虚拟环境

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境（Linux / macOS）
source .venv/bin/activate

# 激活虚拟环境（Windows）
# .venv\Scripts\activate
```

### 3. 安装项目及其依赖

```bash
pip install -e .
```

安装完成后，全局可用 `repoctx` 命令：

```bash
repoctx --help
```

---

## 配置

### 第一步：在项目根目录放置 API Key

系统支持三种方式配置腾讯混元 MaaS API Key，优先级从高到低：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | `.repoctx.yaml` | `model_provider.api_key` 字段 |
| 2 | 环境变量 | `export REPOCTX_TENCENT_API_KEY="your-key"` |
| 3 | `config.ini` | `[DEFAULT]` 节下的 `tencent_cloud_llm_api_key` |

**推荐方式：在项目根目录创建 `config.ini`**

```ini
[DEFAULT]
tencent_cloud_llm_api_key = sk-xxxxxxxxxxxxxxxx
```

> ⚠️ **安全提醒**：`config.ini` 和 `.repoctx.yaml` 必须加入 `.gitignore`，禁止提交到版本仓库。

### 第二步：扫描你的项目

进入你的项目根目录，运行：

```bash
cd /path/to/your-project
repoctx scan
```

首次扫描会自动生成：
- `.repoctx.yaml` —— 项目配置文件
- `.repograph/` —— 知识图谱索引目录
  - `index.json` —— 项目级索引
  - `modules/*.json` —— 模块索引
  - `entities/*.json` —— 实体索引
  - `edges/*.json` —— 关系索引
  - `protected_core.yaml` —— 受保护核心模板
  - `reusable_capabilities.yaml` —— 可复用能力模板

### 第三步：编辑项目配置（可选）

打开生成的 `.repoctx.yaml`，确认或补充项目信息：

```yaml
project_name: your-project
language: python
framework: django
scan_paths:
  - "."
exclude_paths:
  - ".git"
  - ".venv"
  - "node_modules"
  - "__pycache__"
modules:
  - name: backend
    path: backend
    type: backend
  - name: frontend
    path: frontend
    type: frontend
```

> `modules` 字段现在**可选**。如果留空（`modules: []`）或直接省略，系统会根据 `framework` 自动发现模块：
> - `django` —— 自动识别含 `models.py` / `views.py` / `apps.py` 的 Django app
> - `vue` / `nuxt` —— 自动识别 `pages/`、`components/`、`composables/`、`stores/`
> - `fastapi` / `flask` —— 自动识别 `api/`、`models/`、`services/`
> - `generic` —— 自动识别 `src/` 或顶层源码目录
>
> 显式定义的 `modules` 会**覆盖**自动发现结果。建议先运行一次 `repoctx scan` 查看自动发现的结果，再决定是否手动固定。

编辑完成后，重新扫描：

```bash
repoctx scan
```

### 第四步：审核自动生成的受保护核心与可复用能力

扫描完成后，系统会**自动分析**代码结构，为你生成候选的受保护核心和可复用能力，并进入交互式审核：

```
[scan] Found 3 protected core candidates:

  1. backend/auth/views.py
     Reason: Path contains sensitive keywords: ['auth']
     [y]es / [n]o / [e]dit > y

  2. backend/credits/services.py
     Reason: High fan-in: imported by 4 internal files
     [y]es / [n]o / [e]dit > y

[scan] Found 5 reusable capability candidates:

  1. get_available_balance
     File: backend/credits/services.py
     [y]es / [n]o / [e]dit > y
```

- **`y`** —— 确认，写入正式的 `.repograph/protected_core.yaml` 和 `.repograph/reusable_capabilities.yaml`
- **`n`** —— 丢弃该候选
- **`e`** —— 编辑描述后确认

如果你是在 CI / 自动化脚本中运行，不想交互，可以使用 `--auto-approve`：

```bash
repoctx scan --auto-approve
```

这会直接接受所有候选，适合首次初始化或定期重建索引。

如果你错过了交互审核，未确认的候选会被写入 `.repograph/review_protected_core.yaml` 和 `.repograph/review_capabilities.yaml`，你可以手动编辑后再重新扫描。

---

#### 手动微调（可选）

自动分析基于启发式规则（路径关键词、fan-in、跨模块调用等），对于非常核心的业务，建议你在自动生成的文件基础上手动补充或调整。例如：

**`.repograph/protected_core.yaml`**

```yaml
version: "1.0"
cores:
  - id: core-auth
    name: auth/session/login
    type: service
    files:
      - backend/auth/*.py
    modules:
      - auth
    used_by:
      - free_call
      - subscription
    description: Authentication and session management core. Do not modify internals.
    block_policy:
      default_action: block
      required_explanations:
        - Why core change is necessary
      required_evidence:
        - Affected flows list
      require_regression_tests: true
      require_rollback_plan: true
```

**`.repograph/reusable_capabilities.yaml`**

```yaml
version: "1.0"
capabilities:
  - id: cap-balance-check
    name: credit balance check
    description: Get available credit balance for a user.
    module_id: credits
    entry_points:
      - file_path: backend/credits/services.py
        function_name: get_available_balance
        signature: "def get_available_balance(user_id: str) -> int"
        usage_example: "balance = get_available_balance(user_id)"
    use_cases:
      - Before initiating a paid call
    constraints:
      - Do not modify this function for domain-specific logic
```

---

## 快速开始

### 1. 生成任务上下文

```bash
repoctx context "change free call login timing"
```

输出示例：

```
============================================================
RepoCtx Guard — Task Context Report
============================================================

Related Modules:
  • backend
  • frontend

Key Files:
  • backend/auth/views.py
  • frontend/pages/free-call.vue

Reusable Capabilities:
  • credit balance check

Protected Cores (DO NOT MODIFY):
  ⚠ auth/session/login

Risk Points:
  ! Do not modify GA4 event name

Suggested Tests:
  • test_login_flow

============================================================
```

支持 JSON 输出：

```bash
repoctx context "change free call login timing" --format json
```

### 2. 查看当前改动健康度

```bash
repoctx status
```

### 3. Commit 前统一检查

```bash
repoctx commit-check
```

### 4. 分析测试影响

```bash
repoctx test-impact
```

### 5. 运行实验（实验模块）

```bash
repoctx exp run --name exp_v1 --cmd "python train.py --epochs 100"
repoctx exp summarize --run exp_v1
```

---

## CLI 命令参考

| 命令 | 状态 | 说明 |
|------|------|------|
| `repoctx scan` | ✅ 可用 | 扫描项目，生成知识图谱索引 |
| `repoctx context "<task>"` | ✅ 可用 | 根据任务描述生成 AI Coder 上下文 |
| `repoctx status` | 🚧 占位 | 查看当前 working tree 健康度 |
| `repoctx commit-check` | 🚧 占位 | Commit 前统一 Gate 检查 |
| `repoctx test-impact` | 🚧 占位 | 分析测试影响与缺口 |
| `repoctx exp run` | 🚧 占位 | 运行实验并监控 |
| `repoctx exp summarize` | 🚧 占位 | 总结实验结果与双轨诊断 |

> 标注为 🚧 的命令已注册 CLI 框架，内部逻辑正在逐步开发中。

### `repoctx scan` 参数

```bash
repoctx scan [OPTIONS]

Options:
  --auto-approve  Auto-accept all discovered protected cores and capabilities
                  without interactive review.
  --help          Show this message and exit.
```

### `repoctx context` 参数

```bash
repoctx context [OPTIONS] TASK

Options:
  --max-tokens INTEGER  Maximum context length in tokens (default: 3000).
  --format [text|json]  Output format (default: text).
  --help                Show this message and exit.
```

---

## 工程宪法

系统所有行为服从以下七条原则：

1. **AI must not work without project context.** AI 不能在不知道项目上下文的情况下乱改。
2. **New code must not become future legacy debt.** 新代码不能从诞生开始就变成未来屎山。
3. **Every behavior change needs protection.** 任何行为变化都必须有测试、影响分析或明确确认。
4. **Legacy core is production asset, not editable code.** 老项目底层代码是生产资产，不是普通可编辑实现。
5. **Reuse public surfaces, not internal guts.** 复用已有公开能力，不要为了局部需求修改底层实现。
6. **Large changes must be split.** 改动过大必须提醒 commit / split。
7. **Unexpected experimental results must not be automatically rationalized.** 实验结果违反预期时，必须同时怀疑理论和怀疑实现。

---

## 开发说明

### 项目结构

```
repoctx-guard/
├── src/repoctx/
│   ├── cli.py                 # CLI 入口
│   ├── config.py              # 配置占位
│   ├── context_router.py      # Context Router 核心
│   ├── loader.py              # 配置加载与模板生成
│   ├── models/                # Pydantic 数据模型
│   │   ├── config.py
│   │   ├── capability.py
│   │   ├── protected_core.py
│   │   └── rules.py
│   ├── scanner/               # 知识图谱扫描引擎
│   │   ├── engine.py
│   │   ├── file_scanner.py
│   │   ├── module_resolver.py
│   │   ├── entity_extractor.py
│   │   ├── relation_extractor.py
│   │   ├── graph_builder.py
│   │   └── indexer.py
│   ├── llm/                   # LLM 客户端与 Prompt 流水线
│   │   ├── client.py
│   │   ├── pipeline.py
│   │   ├── tokenizer.py
│   │   ├── logger.py
│   │   └── errors.py
│   ├── prompts/               # Prompt 模板
│   │   ├── context_router.txt
│   │   ├── structure_guard.txt
│   │   └── dual_track_diagnosis.txt
│   └── utils/                 # 工具函数
│       ├── yaml_io.py
│       └── project.py
├── tests/                     # 测试套件
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

### 运行测试

```bash
# 运行全部测试
pytest

# 运行特定测试文件
pytest tests/test_scanner.py -v

# 运行集成测试（需要配置真实 API Key）
pytest tests/test_llm_client.py -v -m integration
```

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
