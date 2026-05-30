# RepoCtx Guard — 开发计划文档

> 版本：v1.0-draft  
> 原则：**从运行环境开始搭建，然后逐步细化到每一个 CLI 指令**  
> 约束：本文档只包含计划、步骤与指令定义，不包含可执行代码。

---

## 0. 前置准备（开发启动前）

### 0.1 必读文档

开发开始前，所有参与者必须阅读：

1. `DEVELOPMENT_READINESS.md` — 产品定义、技术规范、数据结构规范
2. `COURSE_DESCRIPTION.md` — 原始需求来源
3. 本文档 — 开发计划与阶段划分

### 0.2 技术栈确认

| 层级 | 选型 | 说明 |
|------|------|------|
| 编程语言 | Python 3.11+ | 类型提示完善、性能足够、生态成熟 |
| 包管理 | `pip` + `requirements.txt` + `pyproject.toml` | 标准 Python 项目结构 |
| CLI 框架 | `click` 或 `typer` | 生成子命令、参数解析、帮助文档 |
| 配置文件解析 | `PyYAML` + `pydantic` | YAML 读写 + 配置校验 |
| 图处理 | `networkx` | 知识图谱的内存图结构 |
| 文件扫描 | `pathlib` + `fnmatch` | 标准库，无需额外依赖 |
| HTTP 客户端 | `httpx` | 异步/同步均支持，API 调用 |
| 文本处理 | `tiktoken` 或等效库 | Token 计数，控制上下文长度 |
| 测试框架 | `pytest` | 单元测试与集成测试 |
| 代码规范 | `ruff` + `mypy` | 静态检查与类型检查 |

### 0.3 开发环境要求

- Python 3.11 或更高版本
- 支持 Linux/macOS/Windows（开发阶段优先 Linux，部署阶段再考虑跨平台）
- 网络环境可访问 `https://tokenhub.tencentmaas.com`
- Git 版本 2.30+

---

## 1. 阶段一：运行环境与项目骨架搭建 ✅ 已完成

### 1.1 目标

建立可运行的最小项目结构，确保后续开发可以在统一的环境中进行。

### 1.2 开发指令（Step-by-Step）

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S1.1 | 创建项目根目录，初始化 Python 虚拟环境 | `python3 -m venv .venv` 成功，激活后 `which python` 指向虚拟环境 |
| S1.2 | 创建 `pyproject.toml`，定义项目元数据、Python 版本约束、入口点 | 文件存在，包含 `name = "repoctx"`、`version = "0.1.0"`、`requires-python = ">=3.11"` |
| S1.3 | 创建 `requirements.txt`，列出所有运行时依赖 | 包含 `click`、`pydantic`、`PyYAML`、`networkx`、`httpx` 等，版本号锁定 |
| S1.4 | 创建 `requirements-dev.txt`，列出开发依赖 | 包含 `pytest`、`ruff`、`mypy` |
| S1.5 | 安装所有依赖 | `pip install -r requirements.txt -r requirements-dev.txt` 无报错 |
| S1.6 | 创建源代码目录结构 `src/repoctx/` | 目录存在，包含 `__init__.py`、`cli.py`、`config.py`（空文件即可） |
| S1.7 | 定义 CLI 入口点，注册 `repoctx` 主命令 | 运行 `python -m repoctx --help` 能输出主命令帮助信息 |
| S1.8 | 注册 6 个子命令占位符（无实现） | 运行 `repoctx scan --help`、`repoctx context --help`、`repoctx status --help`、`repoctx commit-check --help`、`repoctx test-impact --help`、`repoctx exp --help` 均能输出对应子命令的帮助框架 |
| S1.9 | 初始化 Git 仓库，配置 `.gitignore` | `.gitignore` 必须包含 `.venv/`、`__pycache__/`、`.repoctx.yaml`、`.repograph/`、`.env`、`*.egg-info/` |
| S1.10 | 配置 `ruff` 和 `mypy` | `ruff check src/` 和 `mypy src/` 能正常运行（此时可能无代码可检查，但配置必须就绪） |
| S1.11 | 编写第一个集成测试：验证 CLI 入口可用 | `pytest tests/test_cli_exists.py` 通过，验证 6 个子命令均注册成功 |

### 1.3 阶段一产出物

- 完整的 Python 项目骨架
- 可运行的空 CLI（6 个命令均注册了帮助信息）
- 开发依赖全部安装完毕
- 静态检查工具配置就绪
- 一个通过的集成测试

---

## 2. 阶段二：配置系统与数据模型层 ✅ 已完成

### 2.1 目标

建立配置读取、校验、持久化的基础设施。所有后续功能都依赖此层。

### 2.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S2.1 | 实现 `.repoctx.yaml` 的数据模型（Pydantic Model） | 模型包含 `project_name`、`version`、`language`、`framework`、`scan_paths`、`exclude_paths`、`modules`、`model_provider` 等所有字段，支持嵌套校验 |
| S2.2 | 实现配置加载器，支持从项目根目录读取 `.repoctx.yaml` | 给定一个有效的 `.repoctx.yaml` 文件，能正确解析为 Pydantic 对象；文件不存在时抛出明确错误 |
| S2.3 | 实现配置模板生成器，当 `.repoctx.yaml` 不存在时自动生成模板 | 调用 `repoctx scan`（或专门的 init 逻辑）时，在项目根目录生成 `.repoctx.yaml.template`，并提示用户修改 |
| S2.4 | 实现 `model_provider` 配置子模型，含 `api_key`、`base_url`、`model`、`timeout` | 支持从环境变量 `REPOCTX_TENCENT_API_KEY` 覆盖配置文件中的 `api_key` |
| S2.5 | 实现受保护核心索引的数据模型（对应 `protected_core.yaml`） | Pydantic Model 包含 `version`、`updated_at`、`cores` 数组，每条 core 包含 `id`、`name`、`type`、`files`、`modules`、`used_by`、`description`、`block_policy` |
| S2.6 | 实现可复用能力索引的数据模型（对应 `reusable_capabilities.yaml`） | Pydantic Model 包含 `version`、`updated_at`、`capabilities` 数组，每条 capability 包含 `id`、`name`、`description`、`module_id`、`entry_points`、`use_cases`、`constraints`、`related_capabilities` |
| S2.7 | 实现工程规则的数据模型（对应 `project_rules.yaml` 和 `engineering_constitution.yaml`） | 支持规则列表、每条规则含 `pattern`、`severity`、`message` |
| S2.8 | 实现通用 YAML 读写工具类 | 能安全地读写 YAML，处理编码、格式错误、文件锁等问题 |
| S2.9 | 实现项目根目录自动发现（向上递归查找 `.repoctx.yaml`） | 从任意子目录运行 CLI，都能正确找到项目根目录 |
| S2.10 | 编写配置系统的单元测试 | `pytest tests/test_config.py` 全部通过，覆盖有效配置解析、无效配置报错、模板生成、环境变量覆盖等场景 |

### 2.3 阶段二产出物

- 完整的配置数据模型层
- 配置加载/校验/生成/读写工具
- 项目根目录自动发现机制
- 所有 YAML 索引文件的内存模型
- 覆盖配置系统的单元测试

---

## 3. 阶段三：知识图谱扫描引擎（`repoctx scan`） ✅ 已完成

### 3.1 目标

实现第一个完整可用的 CLI 命令 `repoctx scan`，它是整个系统的数据地基。

### 3.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S3.1 | 实现文件扫描器：遍历 `scan_paths`，过滤 `exclude_paths` | 给定一个 Python/Django/Vue 项目目录，能列出所有应被扫描的文件，排除 `__pycache__`、`node_modules`、`.git` 等 |
| S3.2 | 实现模块识别器：根据 `.repoctx.yaml` 中的 `modules` 定义，将文件归属到对应模块 | 每个文件被正确映射到模块 ID；未归属的文件标记为 `unassigned` |
| S3.3 | 实现基础实体提取器：从文件中提取函数、类定义 | 使用正则或 AST 解析，提取 Python 文件的 `def` / `class`、Vue 文件的 `methods` / `computed` 等基础实体 |
| S3.4 | 实现基础关系提取器：简单的文件间 import / include 关系 | 解析 Python 的 `import` / `from ... import`，Vue 的 `import` 语句，建立 `depends_on` 边 |
| S3.5 | 将扫描结果构建为内存图（networkx） | 图节点包含文件、函数、类、模块；边包含 `belongs_to`、`depends_on` |
| S3.6 | 将内存图持久化为 `index.json`、`modules/*.json`、`entities/*.json`、`edges/*.json` | 所有 JSON 文件格式与 `DEVELOPMENT_READINESS.md` 6.2 节定义一致，可人工验证 |
| S3.7 | 实现 `repoctx scan` 命令，整合以上逻辑 | 运行 `repoctx scan` 后，在项目根目录生成 `.repograph/` 目录及全部索引文件 |
| S3.8 | 实现扫描增量更新：仅重新扫描变更文件 | 第二次运行 `repoctx scan` 时，只处理新增/修改/删除的文件，保留未变更部分 |
| S3.9 | 生成 `protected_core.yaml` 模板（如不存在） | 扫描后，若 `.repograph/protected_core.yaml` 不存在，生成包含 5 条示例的模板，并打印提示 |
| S3.10 | 生成 `reusable_capabilities.yaml` 模板（如不存在） | 扫描后，若 `.repograph/reusable_capabilities.yaml` 不存在，生成包含 5 条示例的模板，并打印提示 |
| S3.11 | 编写 `repoctx scan` 的集成测试 | 使用 fixtures 中的示例项目，运行扫描，验证所有输出文件存在且格式正确 |
| S3.12 | 性能基准测试：500 文件项目扫描时间 ≤ 180 秒 | 在测试套件中记录扫描耗时，作为 CI 基准 |

### 3.3 阶段三产出物

- 完整可用的 `repoctx scan` 命令
- 文件扫描、模块识别、实体提取、关系提取四大子模块
- 知识图谱的内存图结构和持久化格式
- 增量扫描能力
- 受保护核心和可复用能力的模板生成
- 集成测试和性能基准

---

## 4. 阶段四：腾讯 MaaS 模型调用层 ✅ 已完成

### 4.1 目标

封装对腾讯混元 MaaS 平台的 API 调用，为后续所有需要 LLM 推理的功能提供统一接口。

### 4.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S4.1 | 实现 HTTP 客户端封装，支持同步 POST 请求 | 基于 `httpx`，封装 `chat_completion()` 函数，接收 `messages`、`model`、`stream` 等参数 |
| S4.2 | 实现认证头自动组装：从配置中读取 `api_key`，生成 `Authorization: Bearer {key}` | 单元测试验证：给定 mock 配置，请求头中包含正确的 Authorization |
| S4.3 | 实现请求体组装：严格遵循 OpenAI-compatible 格式 | 请求体 JSON 包含 `model`、`messages`、`stream`，字段类型和名称正确 |
| S4.4 | 实现响应解析：提取 `choices[0].message.content` | 给定 mock 响应，正确提取文本内容 |
| S4.5 | 实现错误处理：401、429、500、超时、网络不可用的分类处理 | 每种错误抛出不同的异常类型，异常消息包含明确的用户指引 |
| S4.6 | 实现 Token 计数功能：计算 prompt 的 token 数，超过阈值时截断或报错 | 基于 `tiktoken` 或字符估算，确保发送给模型的 prompt 不超过安全阈值 |
| S4.7 | 实现 prompt 模板管理：为不同功能定义不同的 prompt 模板 | 模板存储在 `src/repoctx/prompts/` 目录下，每个功能一个模板文件 |
| S4.8 | 为 Context Router 编写 prompt 模板 | 模板输入：任务描述 + 模块列表 + 文件列表；模板输出：结构化上下文（JSON 格式） |
| S4.9 | 为 Structure Guard 编写 prompt 模板 | 模板输入：新增文件内容 + 项目规则 + 已有模块描述；模板输出：审查报告（JSON 格式） |
| S4.10 | 为双轨诊断编写 prompt 模板 | 模板输入：实验异常描述 + 代码片段 + 理论假设；模板输出：Track A 和 Track B 分析（JSON 格式） |
| S4.11 | 实现 prompt 组装与解析的通用流水线 | 所有模型调用统一经过：模板加载 → 变量填充 → Token 检查 → API 调用 → JSON 解析 → 结果校验 |
| S4.12 | 实现模型调用日志：记录每次调用的请求摘要（脱敏）和响应时间 | 日志写入 `.repograph/logs/llm_calls.log`，不记录 api_key |
| S4.13 | 编写模型调用层的单元测试（全部使用 mock，不调用真实 API） | `pytest tests/test_llm_client.py` 通过，覆盖正常响应、各类错误、Token 截断 |
| S4.14 | 编写一次真实 API 调用测试（标记为 `pytest.mark.integration`，默认跳过） | 手动运行时能通过，验证与腾讯 MaaS 的连通性 |

### 4.3 阶段四产出物

- 统一的 LLM 客户端封装
- 完整的错误处理与重试机制
- Token 计数与安全截断
- 三个核心功能的 prompt 模板（Context Router、Structure Guard、双轨诊断）
- Prompt 组装与解析的通用流水线
- 脱敏的调用日志
- 单元测试 + 集成测试

---

## 5. 阶段五：Context Router（`repoctx context`） ✅ 已完成

### 5.1 目标

实现 `repoctx context "<task>"` 命令，根据用户任务描述生成最小但准确的 AI Coder 上下文。

### 5.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S5.1 | 实现任务描述语义解析：将用户输入的任务字符串进行关键词提取 | 给定 `"change free call login timing"`，能提取关键词 `free call`、`login`、`timing` |
| S5.2 | 实现知识图谱子图匹配：根据关键词在图中搜索相关模块、文件、函数 | 匹配结果包含相关模块 ID、文件路径，按相关度排序 |
| S5.3 | 实现受保护核心交叉检查：如果匹配结果接近受保护核心，加入风险提醒 | 输出中包含 `"不要直接修改 credits core"` 等提醒 |
| S5.4 | 实现可复用能力查询：匹配任务与可复用能力索引 | 输出中包含 `"已有 credits.services.get_available_balance 可复用"` 等提醒 |
| S5.5 | 实现上下文压缩：将匹配到的子图信息压缩为 1500–3000 token 的结构化文本 | 使用 LLM 辅助生成，确保信息完整且不冗余 |
| S5.6 | 组装输出：按固定格式生成结构化上下文报告 | 报告包含：相关模块、关键文件、可复用能力、禁止修改的核心、风险点、建议测试 |
| S5.7 | 实现 `repoctx context "<task>"` 命令 | 运行命令后，终端输出格式化的上下文报告 |
| S5.8 | 支持 `--format json` 参数，输出 JSON 格式 | 解析 JSON 后，包含所有必需字段 |
| S5.9 | 支持 `--max-tokens` 参数，控制上下文长度 | 指定 `--max-tokens 1500` 时，输出被压缩到约 1500 token |
| S5.10 | 编写集成测试：给定 5 个不同任务，验证返回结果包含正确模块和文件 | `pytest tests/test_context_router.py` 通过 |
| S5.11 | 模糊任务处理测试：输入模糊描述时，系统返回澄清问题而非错误 | 验证 `"fix bug"` 这样的输入返回澄清提示 |

### 5.3 阶段五产出物

- 完整可用的 `repoctx context` 命令
- 任务语义解析 + 知识图谱子图匹配引擎
- 受保护核心与可复用能力的交叉提醒
- 上下文压缩与格式化输出
- JSON 输出模式
- 模糊任务处理
- 集成测试覆盖

---

## 5.5 阶段五·五：自动分析与审核交互（Auto Analysis & Review） ⏳ 待开发

> **背景**：原设计中 `protected_core.yaml` 和 `reusable_capabilities.yaml` 要求用户手动填写，这与系统初衷（解决大项目 track 不过来）相矛盾。本阶段将其改为**系统自动分析 + 用户审核确认**的模式。

### 5.5.1 目标

`repoctx scan` 完成后，系统自动分析知识图谱，生成候选的受保护核心和可复用能力列表，通过 CLI 交互让用户批量审核确认，最终固化到 YAML 索引中。

### 5.5.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S5.5.1 | **自动模块发现**：根据 `framework` 和目录结构自动推断模块 | Django 项目自动识别每个 app 为模块；Vue/Nuxt 识别 pages/components/composables；FastAPI/Flask 识别 api/models/services；Generic 识别 src/ 下的一级子目录 |
| S5.5.2 | 用户可覆盖自动发现的模块：`modules` 字段退化为**修正列表** | 自动推断后，用户只需在 `.repoctx.yaml` 中补充推断错误的模块，或删除不需要的模块 |
| S5.5.3 | **受保护核心自动识别**：基于高扇入、调用链、路径关键词生成候选核心 | 规则：被 >=3 个模块 import 的文件（高扇入）；被 >=10 个文件 import 的文件（高频调用）；路径含 `auth`/`session`/`payment`/`billing`/`core` 关键词；公开接口但无测试覆盖 |
| S5.5.4 | **可复用能力自动识别**：基于多模块调用、公开接口、稳定签名生成候选能力 | 规则：被 >=2 个模块调用的函数/类；非 `_private` 且被外部 import 的函数；utils/services 目录下被多处调用的函数 |
| S5.5.5 | **CLI 审核交互**：扫描完成后在终端输出审核报告 | 报告列出候选核心/能力，每项显示：文件路径、被调用次数、建议级别（PROTECTED / REUSABLE）、用户操作提示（y=确认/n=跳过/e=编辑） |
| S5.5.6 | 支持**批量确认模式**：`repoctx scan --auto-approve` | 信任自动分析结果，无需交互直接固化 |
| S5.5.7 | 支持**审核文件模式**：生成 `.repograph/review_protected_core.yaml` 和 `.repograph/review_capabilities.yaml` | 用户可手动编辑审核草稿，再运行 `repoctx scan --apply-review` 固化 |
| S5.5.8 | 编写集成测试：验证自动分析在示例项目上的准确率 | 测试覆盖：Django/Vue/Generic 三种框架的模块推断；高扇入文件识别；公开接口识别 |
| S5.5.9 | 编写用户可覆盖的测试：验证手动修正优先级高于自动推断 | 用户在 `.repoctx.yaml` 中定义的模块应覆盖自动推断结果 |

### 5.5.3 产出物

- 自动模块发现引擎（框架感知）
- 受保护核心自动分析引擎（高扇入 + 关键词 + 调用链）
- 可复用能力自动分析引擎（多模块调用 + 公开接口）
- CLI 审核交互（逐条确认 / 批量确认 / 审核文件模式）
- `modules` 字段从"必填列表"退化为"修正覆盖列表"
- 审核草稿文件（`review_protected_core.yaml`、`review_capabilities.yaml`）
- 集成测试覆盖三种框架的自动推断

---

## 6. 阶段六：Structure Guard（`repoctx status` 的结构检查部分）

实现新代码的结构检查能力，为 `repoctx status` 和 `repoctx commit-check` 提供 Structure Guard 引擎。

### 6.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S6.1 | 实现 Git 变更集捕获：获取当前 working tree 的所有新增/修改/删除文件 | 与 `git diff --name-status` 结果一致 |
| S6.2 | 实现变更文件内容读取：读取新增/修改文件的内容 | 能正确读取文本文件，跳过二进制文件 |
| S6.3 | 实现规则引擎：加载 `project_rules.yaml` 和 `engineering_constitution.yaml`，编译为可执行规则 | 规则匹配基于文件路径模式、文件名模式、内容模式 |
| S6.4 | 实现文件位置检查：新文件是否放在了错误的目录 | 例：`backend/utils/payment_helper.py` 应被标记为 `"billing-specific logic 不应放进全局 utils"` |
| S6.5 | 实现职责单一检查：通过 LLM 分析新 service / util 的职责是否单一 | 调用模型，输入文件内容 + 已有模块描述，输出审查意见 |
| S6.6 | 实现硬编码与临时逻辑检测：识别魔法数字、TODO、FIXME、临时注释 | 基于正则匹配，标记为 warning |
| S6.7 | 实现重复实现检测：将新函数与已有可复用能力索引对比 | 相似度超过阈值时，提示复用已有能力 |
| S6.8 | 组装 Structure Guard 审查报告 | 每条审查项包含：类型、涉及文件、问题描述、严重程度、建议操作、违反的宪法条款 |
| S6.9 | 编写 Structure Guard 的单元测试 | 使用 fixtures 中的示例代码片段，验证各类违规检测的准确性 |

### 6.3 阶段六产出物

- Git 变更集捕获工具
- 规则引擎（文件位置、命名、模块边界、跨模块调用）
- LLM 辅助的职责分析与重复检测
- 硬编码与临时逻辑检测
- 结构审查报告生成器
- 单元测试

---

## 7. 阶段七：Test Impact & Regression Guard（`repoctx test-impact`） ⏳ 待开发

### 7.1 目标

实现 `repoctx test-impact` 命令，分析变更对测试的影响，识别测试缺口。

### 7.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S7.1 | 实现测试文件发现：根据项目语言和框架，自动发现测试文件 | Python 项目识别 `test_*.py` 和 `*_test.py`；前端项目识别 `*.spec.ts`、`.test.ts`、Playwright 测试等 |
| S7.2 | 建立测试到被测代码的映射：解析测试文件，提取被测模块/函数 | 基于 import 语句和测试函数名推断映射关系 |
| S7.3 | 实现变更影响范围分析：根据变更文件，反向查找影响到的测试 | 修改 `credits/services.py` 时，能找出 `test_credit_balance`、`test_free_call_credit_check` 等 |
| S7.4 | 实现测试缺口识别：分析变更引入的新逻辑，判断是否有测试覆盖 | 如果新增了一个 if 分支但测试未覆盖，标记为缺失 |
| S7.5 | 实现旧 case 影响预测：基于调用链分析，列出可能因变更而失败的已有测试 | 修改公共函数时，列出所有调用该函数的测试 |
| S7.6 | 实现 `repoctx test-impact` 命令 | 输出：建议运行的测试、缺失的测试、可能受影响的旧 case |
| S7.7 | 支持 `--format json` 参数 | JSON 输出包含测试列表和缺口列表 |
| S7.8 | 编写集成测试：使用 fixtures 验证影响分析准确性 | `pytest tests/test_test_impact.py` 通过 |

### 7.3 阶段七产出物

- 测试文件自动发现器
- 测试到代码的映射索引
- 变更影响范围反向查找引擎
- 测试缺口识别器
- 旧 case 影响预测器
- `repoctx test-impact` 命令
- 集成测试

---

## 8. 阶段八：Legacy Core Guardian（`repoctx commit-check` 的核心保护部分） ⏳ 待开发

### 8.1 目标

实现受保护核心检查和可复用能力提醒，为 `repoctx commit-check` 提供核心资产保护能力。

### 8.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S8.1 | 实现受保护核心交叉检测：将变更集文件路径与 `protected_core.yaml` 中的 `files` 模式进行匹配 | 修改 `backend/credits/services.py` 时，正确识别为触碰了受保护核心 |
| S8.2 | 实现触碰提醒生成：列出被修改的核心、用途、影响流 | 提醒包含 `"This file is used by free_call, free_text, subscription, verification_channel"` |
| S8.3 | 实现审批材料检查：验证用户是否提供了全部必需材料 | 检查：必要性解释、替代方案证明、影响流清单、回归测试、回滚方案 |
| S8.4 | 实现可复用能力语义匹配：将新增代码的意图与 `reusable_capabilities.yaml` 匹配 | 当用户要写 balance check 时，提示 `"已有 credits.services.get_available_balance，请复用"` |
| S8.5 | 实现可复用能力提醒生成：包含能力名称、入口点、使用示例、扩展建议 | 提醒格式与 `DEVELOPMENT_READINESS.md` 4.4.4 节定义一致 |
| S8.6 | 实现审批记录写入：受保护核心修改审批记录写入 `.repograph/protected_core_modification_log.yaml` | 记录包含：时间、修改人、核心 ID、影响流、审批结果 |
| S8.7 | 编写 Legacy Core Guardian 的单元测试 | 覆盖：触碰检测、能力匹配、审批材料校验 |

### 8.3 阶段八产出物

- 受保护核心交叉检测器
- 触碰提醒生成器
- 审批材料检查器
- 可复用能力语义匹配器
- 审批记录持久化
- 单元测试

---

## 9. 阶段九：Commit Gate（`repoctx commit-check`） ⏳ 待开发

### 9.1 目标

实现 `repoctx commit-check` 命令，作为 Commit 前的统一 Gate，汇总所有检查结果。

### 9.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S9.1 | 实现变更集汇总：文件数、行数、涉及模块数、是否跨前后端 | 与 `repoctx status` 共享变更集捕获逻辑 |
| S9.2 | 集成 Structure Guard：运行结构检查，收集审查报告 | 输出所有结构问题 |
| S9.3 | 集成 Test Impact：运行测试影响分析，收集建议 | 输出测试建议和缺失 |
| S9.4 | 集成 Legacy Core Guardian：运行核心保护检查 | 输出触碰核心提醒或可复用能力建议 |
| S9.5 | 实现 Gate 决策逻辑：汇总所有检查结果，判定 pass / block | 存在任何 `blocker` 级别问题时，结论为 `block`；只有 `warning` 和 `suggestion` 时为 `pass`（但列出所有问题） |
| S9.6 | 实现统一报告格式化：终端输出带颜色、分区块 | blocker 用红色、warning 用黄色、suggestion 用灰色 |
| S9.7 | 实现 `repoctx commit-check` 命令 | 运行命令后输出完整 Gate 报告 |
| S9.8 | 支持 `--format json` 参数 | JSON 包含：总体结论、各模块检查列表、所有 blocker 详情 |
| S9.9 | 编写集成测试：模拟不同变更集，验证 Gate 决策正确 | `pytest tests/test_commit_check.py` 通过，覆盖：干净变更（pass）、结构违规（block）、触碰核心（block）、缺测试（warning） |

### 9.3 阶段九产出物

- 完整可用的 `repoctx commit-check` 命令
- 变更集汇总 + 三大检查模块的集成
- Gate 决策引擎
- 统一报告格式化
- JSON 输出模式
- 集成测试

---

## 10. 阶段十：`repoctx status` ⏳ 待开发

### 10.1 目标

实现 `repoctx status` 命令，作为开发过程中的持续健康度检查工具。

### 10.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S10.1 | 复用阶段六的变更集捕获逻辑 | 与 `commit-check` 使用同一套变更集分析 |
| S10.2 | 实现改动统计：文件数、新增行数、删除行数 | 与 `git diff --stat` 结果一致 |
| S10.3 | 实现模块影响分析：涉及哪些模块 | 基于知识图谱映射变更文件到模块 |
| S10.4 | 实现跨前后端检测：变更是否同时涉及 frontend 和 backend | 基于 `.repoctx.yaml` 中的模块类型标记判断 |
| S10.5 | 实现测试文件变更检测：变更集中是否包含测试文件 | 如果没有测试文件变更且存在业务代码变更，标记为黄色 warning |
| S10.6 | 实现受保护核心触碰检测（轻量版） | 与 `commit-check` 共享逻辑，但只输出提醒不阻断 |
| S10.7 | 实现健康度评级算法 | 综合以上因素，输出 `green` / `yellow` / `red` |
| S10.8 | 实现 commit 建议：根据健康度给出建议 | green → 建议提交；yellow → 建议补充测试/检查；red → 建议拆分或修复 |
| S10.9 | 实现 `repoctx status` 命令 | 终端输出格式化的健康度报告 |
| S10.10 | 支持 `--watch` 参数（可选，如实现成本不高） | 持续监听文件变更，实时更新状态 |
| S10.11 | 编写集成测试 | `pytest tests/test_status.py` 通过 |

### 10.3 阶段十产出物

- 完整可用的 `repoctx status` 命令
- 变更统计、模块影响、跨端检测、测试检测、核心触碰检测
- 健康度评级算法
- Commit 建议
- 集成测试

---

## 11. 阶段十一：Experiment Intelligence Agent（`repoctx exp run / summarize`） ⏳ 待开发

### 11.1 目标

实现实验管理模块，包含实验运行、监控、总结、双轨诊断。

### 11.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S11.1 | 实现实验目录结构定义：`.repograph/experiments/<name>/` | 子目录包含 `config.yaml`、`logs/`、`results/`、`summary.yaml` |
| S11.2 | 实现实验配置数据模型：名称、命令、配置、环境、预期指标 | Pydantic Model 与 `DEVELOPMENT_READINESS.md` 6.6 节一致 |
| S11.3 | 实现预检逻辑：环境检查、依赖检查、输入数据检查、资源检查 | 预检失败时输出明确原因，终止实验 |
| S11.4 | 实现 `repoctx exp run --name <name> --cmd <cmd>` 命令 | 运行命令后启动实验进程，后台运行 |
| S11.5 | 实现运行时监控：进程存活检测、超时检测 | 超时时间从配置读取，默认 4 小时；超时后发送告警 |
| S11.6 | 实现运行时日志捕获：重定向 stdout/stderr 到实验日志文件 | 日志文件位于 `.repograph/experiments/<name>/logs/` |
| S11.7 | 实现 `repoctx exp summarize --run <name>` 命令 | 读取实验日志和结果，生成 Post-Run Summary |
| S11.8 | 实现指标提取：从日志中解析关键指标（正则或配置指定格式） | 能提取 loss、accuracy 等训练指标 |
| S11.9 | 实现异常识别：检测日志中的错误、警告、指标突变 | 基于关键词匹配和阈值判断 |
| S11.10 | 实现双轨诊断：当结果异常时，调用 LLM 生成 Track A 和 Track B 分析 | 使用阶段四的 prompt 模板，输出结构化诊断报告 |
| S11.11 | 实现下一步建议生成：基于诊断结果生成具体建议 | 建议必须可执行、可量化 |
| S11.12 | 实现实验记忆写入：将完整实验记录写入 `.repograph/experiments/<name>.yaml` | 格式与 `DEVELOPMENT_READINESS.md` 6.6 节一致 |
| S11.13 | 实现通知机制（可选，MVP 可延后）：Slack / Email 通知 | 使用 webhook 或 SMTP，通知实验完成状态和摘要 |
| S11.14 | 编写集成测试：模拟一次完整实验（命令用 `sleep` 模拟） | 验证预检、运行、监控、总结全流程 |

### 11.3 阶段十一产出物

- 完整可用的 `repoctx exp run` 和 `repoctx exp summarize` 命令
- 实验目录结构管理
- 预检、运行、监控、总结全流程
- 指标提取、异常识别
- 双轨诊断（核心功能）
- 实验记忆持久化
- 集成测试

---

## 12. 阶段十二：集成测试、验收与文档收尾 ⏳ 待开发

### 12.1 目标

对整个系统进行全面测试，修复缺陷，完善文档，达到可发布状态。

### 12.2 开发指令

| 步骤 | 指令/动作 | 验收标准 |
|------|----------|---------|
| S12.1 | 编写端到端测试：从空项目开始，执行完整的标准研发任务闭环 | 包含：scan → context → 修改代码 → status → test-impact → commit-check |
| S12.2 | 编写端到端测试：执行完整的实验管理闭环 | 包含：exp run → 模拟运行 → exp summarize → 验证输出 |
| S12.3 | 性能测试：500 文件项目，`repoctx scan` ≤ 180 秒 | 记录基准数据 |
| S12.4 | 性能测试：`repoctx context` ≤ 5 秒 | 记录基准数据 |
| S12.5 | 性能测试：`repoctx commit-check` ≤ 10 秒 | 记录基准数据 |
| S12.6 | 安全审计：检查 `.repoctx.yaml` 是否在 `.gitignore` 中 | 脚本自动检查 |
| S12.7 | 安全审计：确认代码中无硬编码 API Key | `grep -r "sk-" src/` 无结果 |
| S12.8 | 代码质量检查：运行 `ruff check src/` | 无 blocker 级别问题 |
| S12.9 | 类型检查：运行 `mypy src/` | 无类型错误 |
| S12.10 | 测试覆盖率检查：运行 `pytest --cov=src/repoctx` | 核心模块覆盖率 ≥ 70% |
| S12.11 | 编写用户文档：README.md | 包含安装、配置、6 个命令的使用示例 |
| S12.12 | 编写配置模板说明文档：如何填写 `protected_core.yaml` 和 `reusable_capabilities.yaml` | 文档存在，含示例 |
| S12.13 | 编写模型调用说明：如何配置腾讯 API Key | 文档存在，含获取 Key 的指引 |
| S12.14 | 最终验收：对照 `DEVELOPMENT_READINESS.md` 第 9 章验收标准逐条验证 | 全部通过 |

### 12.3 阶段十二产出物

- 端到端测试套件
- 性能基准数据
- 安全审计报告
- 代码质量与类型检查通过
- 测试覆盖率达标
- 用户文档（README、配置说明、API Key 配置说明）
- 最终验收通过

---

## 13. 开发顺序总览

| 阶段 | 名称 | 核心产出 | 依赖阶段 |
|------|------|---------|---------|
| 1 | 环境与骨架 | 可运行的空 CLI | — |
| 2 | 配置与模型层 | 配置系统、数据模型 | 1 |
| 3 | 扫描引擎 | `repoctx scan` | 2 |
| 4 | 模型调用层 | LLM 客户端、prompt 模板 | 2 |
| 5 | Context Router | `repoctx context` | 3, 4 |
| 5.5 | 自动分析与审核交互 | 自动模块/核心/能力发现 + CLI 审核 | 3, 4, 5 |
| 6 | Structure Guard | 结构检查引擎 | 3, 4, 5.5 |
| 7 | Test Impact | 测试影响分析 | 3 |
| 8 | Legacy Core | 核心保护引擎 | 2 |
| 9 | Commit Gate | `repoctx commit-check` | 6, 7, 8 |
| 10 | Status | `repoctx status` | 6, 8 |
| 11 | Experiment Agent | `repoctx exp run/summarize` | 2, 4 |
| 12 | 集成与验收 | 完整系统 + 文档 | 全部 |

---

## 14. 风险与缓解策略

| 风险 | 影响 | 缓解策略 |
|------|------|---------|
| 腾讯 MaaS API 不稳定或变更接口 | 高 | 封装层做好版本隔离，预留切换到其他模型提供商的接口；错误处理做好降级（如返回本地规则检查结果） |
| LLM 输出不稳定（JSON 格式不固定） | 高 | prompt 中要求严格 JSON 格式；输出后用 pydantic 校验，失败时重试或返回安全默认值 |
| 知识图谱扫描性能差 | 中 | 先做基础版（正则+AST），后续迭代引入增量扫描和缓存；大型项目可跳过细粒度实体提取 |
| 受保护核心索引维护成本高 | 中 | ~~MVP 阶段要求手动维护~~ → 已由阶段 5.5 的自动分析解决；用户只需审核，无需从零手写 |
| 自动分析误判 | 中 | 提供审核交互机制（y/n/e），允许用户覆盖自动推断结果；高置信度结果可批量确认 |
| 测试映射不准确 | 中 | 先做基于 import 关系的静态映射，后续迭代引入动态覆盖率分析 |
| Token 成本过高 | 低 | 控制 prompt 长度，缓存相似请求的响应，批量处理审查项 |

---

## 15. 附录：每日/每周开发节奏建议

### 15.1 日常开发节奏

- **每天开始**：运行 `ruff check src/` 和 `mypy src/`，修复遗留问题
- **每个功能开发**：先写测试（TDD），再写实现，最后跑通测试
- **每个阶段结束**：提交一个功能完整的 commit，确保该阶段所有验收标准通过
- **每周末**：运行完整测试套件，检查覆盖率和性能基准

### 15.2 里程碑检查点

| 检查点 | 时间建议 | 检查内容 |
|--------|---------|---------|
| CP-1 | 阶段 3 结束 | `repoctx scan` 能正确扫描并生成索引 |
| CP-2 | 阶段 4 结束 | 能成功调用腾讯 MaaS API 并返回正确响应 |
| CP-3 | 阶段 5 结束 | `repoctx context` 能生成结构化上下文 |
| CP-3.5 | 阶段 5.5 结束 | `repoctx scan` 能自动推断模块、核心、能力，用户只需审核确认 |
| CP-4 | 阶段 9 结束 | `repoctx commit-check` 能阻止触碰核心的提交 |
| CP-5 | 阶段 11 结束 | 能完整运行一次实验并生成双轨诊断 |
| CP-6 | 阶段 12 结束 | 系统通过全部验收标准，可交付 |

---

> 本文档为 RepoCtx Guard 的开发计划，指导从环境搭建到每个 CLI 指令的逐步实现。开发过程中如需调整计划，必须同步更新本文档，确保计划与实际一致。
