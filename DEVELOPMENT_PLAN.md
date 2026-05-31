# Repo Semantic Memory & Engineering Guard — 开发计划与进度

> 版本：v2.0-rewrite  
> 基于 `COURSE_DESCRIPTION.md` 重写后的开发计划。旧 v1.0 设计已废弃，不再维护。  
> 本文档同时承担 **开发计划** + **进度追踪** 双重职责，每完成一个阶段后更新对应状态。

---

## 0. 产品重新定位

**名称**：Repo Semantic Memory & Engineering Guard  
**中文**：面向 AI coder 的项目语义记忆与工程守卫系统  
**一句话**：一个给 AI coder 使用的项目语义记忆层——从入口函数消化代码，沉淀调用链语义，持续刷新项目理解，让不同 coder session 共享同一份稳定上下文，并基于这份语义记忆做结构、测试、老代码和实验守卫。

**旧定位（已废弃）**：轻量 repo scanner + context router  
**新定位**：入口驱动的语义消化系统 + 持续更新的语义记忆层 + 基于语义记忆的工程守卫

### 0.1 核心变化

| 维度 | 旧设计 | 新设计 |
|------|--------|--------|
| 核心问题 | "项目里有哪些文件？" | "从这个入口进去，代码实际做了什么？" |
| 理解方式 | 每次 session 重新 scan | 沉淀为可复用的语义资产（card） |
| Guard 基础 | 路径规则 + 关键词匹配 | 语义记忆（调用链、业务角色、副作用） |
| 起点 | 语义描述 `"改登录流程"` | 入口文件 `digest-entry views.py` |
| 输出 | 文件列表 + 风险提示 | Entry Card + Path Card + Symbol Card + Context Pack |

### 0.2 工程宪法（不变）

| 编号 | 原则 |
|------|------|
| EC-1 | 项目理解必须沉淀，而不是每个 coder session 重新生成。 |
| EC-2 | 入口点是自然起点。真实屎山项目里，人通常只知道入口。 |
| EC-3 | 语义记忆是 truth source。多个 coder session 必须读同一份语义记忆。 |
| EC-4 | 语义记忆必须版本化且可刷新。代码改了，沉淀内容必须能检测过期并更新。 |
| EC-5 | Guards 基于语义记忆，不是路径规则。 |
| EC-6 | 老底层代码默认不可改，只能通过 public surface 安全复用。 |
| EC-7 | 实验异常必须同时怀疑理论和怀疑实现。 |

---

## 1. 术语表

| 术语 | 定义 |
|------|------|
| **Semantic Card** | 语义资产卡片，描述代码的语义角色而非结构。类型：entry / path / symbol / flow。 |
| **Entry Card** | 描述一个入口函数的业务职责、主调用链、业务角色。 |
| **Path Card** | 描述一个入口下的主要业务路径，含 steps 和 branches。 |
| **Symbol Card** | 描述深层函数/服务/模型的项目语义角色、副作用、复用指导。 |
| **Context Pack** | 给 coder 直接读的压缩上下文文档，汇总入口、路径、重要函数、陷阱。 |
| **Call Graph** | 从入口函数递归追踪调用链得到的树状结构。 |
| **Semantic Diff** | 总结代码改动带来的业务语义变化，而非文件级 diff。 |
| **Task Workspace** | 单个需求的共享任务理解层，包含 accepted_understanding、change_plan、frozen_assumptions 等。 |
| **Protected Semantic Entity** | 受保护的生产资产，不是路径而是语义实体（如 `credits.services.consume_credits`）。 |

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     CLI (repoctx)                           │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│  Semantic   │   Task      │   Guards    │   Experiment      │
│   Memory    │  Workspace  │             │    Agent          │
├─────────────┼─────────────┼─────────────┼───────────────────┤
│digest-entry │task start   │status       │exp init           │
│stale        │task export  │structure-   │exp check          │
│refresh      │validate     │  check      │exp run            │
│semantic-diff│             │test-impact  │exp summarize      │
│export-context│            │legacy-check │exp diagnose       │
│             │             │commit-check │                   │
└─────────────┴─────────────┴─────────────┴───────────────────┘
        │              │              │              │
        └──────────────┴──────────────┴──────────────┘
                           │
              ┌────────────┴────────────┐
              │    Semantic Memory      │
              │      Engine             │
              │  (CallGraphTracer +     │
              │   SemanticDigestEngine) │
              └────────────┬────────────┘
                           │
              ┌────────────┴────────────┐
              │     LLM Client Layer    │
              │  (Prompt Pipeline +     │
              │   Token Counter +       │
              │   Call Logger)          │
              └─────────────────────────┘
```

---

## 3. 数据模型

### 3.1 Card 基类

```yaml
# 所有 card 共享的结构
card_type: entry | path | symbol | flow
id: "entry.free_call.start_free_call"
version:
  code_hash: "sha256 of source file"
  dependency_hash: "sha256 of downstream symbols"
  git_commit: "9f1a2c"
  generated_at: "2026-05-31T12:00:00Z"
  status: fresh | stale | deprecated
```

### 3.2 Entry Card

```yaml
card_type: entry
id: entry.free_call.start_free_call
source:
  file: secondline/views/free_call_views.py
  symbol: start_free_call
  line_start: 12
  line_end: 45
summary: >
  Starts the free call flow from the web entrypoint.
  Resolves user/session state, validates request data,
  checks call eligibility and credit state, creates call records,
  invokes the call provider, and returns call status to the frontend.
business_role:
  - free call start entrypoint
  - request validation boundary
  - call orchestration entry
main_downstream:
  - free_call.services.start_call
  - credits.services.get_available_balance
  - call_provider.client.start_call
  - analytics.track_free_call_event
```

### 3.3 Path Card

```yaml
card_type: path
id: path.free_call.start.success
entry: entry.free_call.start_free_call
condition: user is authenticated and eligible for free call
steps:
  - parse request
  - resolve account
  - validate phone number
  - check eligibility
  - create call record
  - invoke provider
  - emit tracking event
  - return success response
branches:
  unauthenticated:
    summary: unauthenticated user is blocked or receives login-required response
  insufficient_credit:
    summary: user cannot start call and may be redirected to earn credits
  provider_failure:
    summary: call provider failed; call record should not remain in success state
```

### 3.4 Symbol Card

```yaml
card_type: symbol
id: symbol.credits.get_available_balance
source:
  file: backend/credits/services.py
  symbol: get_available_balance
  line_start: 12
  line_end: 18
summary: >
  Public read surface for obtaining the user's available credit balance.
  Should be reused by features that need balance display or eligibility checking.
semantic_role:
  - credit balance read surface
  - shared service
side_effects: none
used_by_flows:
  - free_call.start
  - free_text.send
  - subscription.renewal
reuse_guidance:
  use_when:
    - checking eligibility
    - displaying balance
  avoid:
    - duplicating balance calculation
    - directly reading raw balance fields
```

### 3.5 Context Pack

```markdown
# Context Pack: Free Call Flow

## Flow Summary
Free Call starts from the frontend dial action and eventually invokes
the backend call start endpoint. The flow resolves auth/session state,
checks call eligibility, interacts with credit services, creates call
records, invokes the provider, and emits tracking events.

## Main Entrypoints
- `start_free_call`
- `check_free_call_status`
- `free_call_callback`

## Main Start Path
`DialPad.onDialClick` → `useAuthGuard` → `freeCallApi.startCall`
→ `start_free_call` → `free_call.services.start_call`
→ `credits.services.get_available_balance` → `call_provider.start_call`
→ `track_free_call_event`

## Important Deep Functions
- `credits.services.get_available_balance`: public credit read surface.
- `credits.services.consume_credits`: state mutation core, used by multiple flows.
- `call_provider.start_call`: external provider side effect.

## Known Pitfalls
- Do not duplicate credit balance logic.
- Auth timing changes usually belong near frontend action/auth guard.
- Provider callback logic is separate from initial call start.
- GA4 event names may be used by funnel analysis.

## Related Tests
- backend free call start tests
- credit insufficiency tests
- frontend free call E2E tests
```

---

## 4. 命令体系

### 4.1 Semantic Memory

| 命令 | 状态 | 说明 |
|------|------|------|
| `repoctx digest-entry <file>` | ✅ 已完成 | 入口语义消化，生成 card |
| `repoctx stale` | ✅ 已完成 | 检查过期语义资产 |
| `repoctx refresh --affected` | ✅ 已完成 | 增量刷新 card |
| `repoctx semantic-diff --since main` | ⏳ 待开发 | 语义变化总结 |
| `repoctx export-context <flow>` | ⏳ 待开发 | 导出 context pack |

### 4.2 Task Workspace

| 命令 | 状态 | 说明 |
|------|------|------|
| `repoctx task start "name" --entry <file::sym>` | ✅ 已完成 | 创建任务工作区 |
| `repoctx task list` | ✅ 已完成 | 列出所有任务工作区 |
| `repoctx task export <id>` | ✅ 已完成 | 导出任务上下文 |
| `repoctx task status <id>` | ✅ 已完成 | 查看任务状态 |
| `repoctx task validate <id>` | ✅ 已完成 | 验证 diff 是否违背任务约束 |

### 4.3 Guards

| 命令 | 状态 | 说明 |
|------|------|------|
| `repoctx status` | ⏳ 待开发 | working tree 健康度 |
| `repoctx structure-check` | ⏳ 待开发 | 新代码结构检查 |
| `repoctx test-impact --task <id>` | ⏳ 待开发 | 测试影响分析 |
| `repoctx legacy-check` | ⏳ 待开发 | 老代码保护检查 |
| `repoctx commit-check` | ⏳ 待开发 | commit 前统一 gate |

### 4.4 Experiment Agent

| 命令 | 状态 | 说明 |
|------|------|------|
| `repoctx exp init` | ⏳ 待开发 | 初始化实验工作区 |
| `repoctx exp check --config <cfg>` | ⏳ 待开发 | 实验前检查 |
| `repoctx exp run --name <n> --cmd "cmd"` | ⏳ 待开发 | 运行实验 |
| `repoctx exp summarize <run_id>` | ⏳ 待开发 | 实验总结 |
| `repoctx exp diagnose <run_id>` | ⏳ 待开发 | 双轨诊断 |

---

## 5. 文件结构

```
.repograph/
  semantic_memory/
    entries/
      entry.free_call.start_free_call.yaml
    paths/
      path.free_call.start.success.yaml
    symbols/
      symbol.credits.get_available_balance.yaml
    flows/
      flow.free_call.yaml
    context_packs/
      free_call.md
    versions/
      semantic_memory_v001.yaml
  tasks/
    free_call_login_timing/
      task_intent.md
      accepted_understanding.md
      relevant_context_pack.md
      change_plan.md
      active_files.yaml
      out_of_scope.yaml
      frozen_assumptions.yaml
      session_notes/
      semantic_diff.md
  guards/
    engineering_constitution.yaml
    structure_rules.yaml
    test_rules.yaml
    legacy_rules.yaml
  legacy/
    protected_entities.yaml
    reusable_capabilities.yaml
    public_surfaces.yaml
    core_contracts.yaml
  tests/
    behavior_test_map.yaml
    test_impact_map.yaml
  experiments/
    runs/
    summaries/
    environment_notes/
    failure_modes/
    design_specs/
  reports/
    commit_checks/
    semantic_diffs/
    experiment_summaries/
```

---

## 6. 开发路线图

### Phase 0：基础设施准备 ✅ 已完成

- [x] 清理旧 CLI（scan / context / entry_context 命令已废弃，保留 exp 占位）
- [x] 新建目录结构：`semantic_memory/`, `tracer/`, `cards/`
- [x] 新建 Card 数据模型（EntryCard, PathCard, SymbolCard, ContextPack, CardVersion）
- [x] 新建 CLI 命令注册（digest-entry, stale, refresh, semantic-diff, export-context, task, guards, exp）
- [x] 新建 `semantic_memory/engine.py`（stub 版本，打通 CLI → tracer → persistence 链路）
- [x] 新建 `.repograph/` 目录初始化逻辑（`repoctx init` 或自动初始化）

### Phase 1：入口调用链追踪器 ✅ 已完成

- [x] `ImportResolver`：从 AST 提取 import 映射表
- [x] `CallExtractor`：从函数体 AST 提取 Call 节点
- [x] `ModulePathResolver`：模块路径 → 文件路径
- [x] `CallGraphTracer`：递归追踪调用链，输出 CallTree
- [x] 扩展性设计：`BaseTracer` 抽象基类 + `TracerFactory` 按扩展名分发，为未来 JS/Vue/Go 等语言预留插件位
- [x] 测试：22 个测试全部通过（import 解析、call 提取、模块路径解析、端到端追踪、factory 分发）

**当前进度**：
- `src/repoctx/tracer/base.py` — `BaseTracer` 抽象基类 + `CallNode`/`CallTree`/`TracerContext`
- `src/repoctx/tracer/factory.py` — 扩展名分发工厂
- `src/repoctx/tracer/python/` — Python 专用追踪器（继承 `BaseTracer`）
  - `import_resolver.py` — 支持 `import X`、`from X import Y`、`from X import Y as Z`、相对导入
  - `call_extractor.py` — AST `Call` 节点提取
  - `module_resolver.py` — 模块路径 → `.py` / `__init__.py` 文件路径
  - `tracer.py` — `PythonTracer`，递归追踪 + 循环调用防护（visited set）+ 深度限制

### Phase 2：Card 生成器

- [x] `SemanticDigestEngine.digest()`：基于 CallTree 生成 Entry Card、Symbol Cards
- [x] LLM Prompt 模板：Entry Card prompt、Symbol Card prompt、Context Pack prompt
- [x] 代码 hash 计算（SHA256）
- [x] git commit 读取
- [x] Card 写入 `.repograph/semantic_memory/`
- [x] 增量持久化：失败不丢前面已生成的 card
- [x] JSON 解析容错（自动修复 trailing comma）
- [x] 智能跳过：code_hash 未变则跳过 LLM，节省 token
- [x] `--force` 选项强制重新生成
- [x] `repoctx list` 查看所有 cards
- [x] `repoctx stale` 检测 code_hash 变化的 cards
- [x] `repoctx delete-card <id>` 删除指定 card
- [x] 测试：验证生成内容的语义质量

### Phase 3：CLI 端到端 ✅ 已完成

- [x] `repoctx digest-entry` 打通 tracer → engine → persistence 全链路
- [x] 支持 `--only` 和 `--depth`
- [x] 支持 `--output-dir`
- [x] 端到端测试

### Phase 4：版本化与刷新 ✅ 已完成

- [x] `repoctx stale`：检测 code_hash 变化的 card
- [x] `repoctx refresh --affected`：增量刷新过期 card
  - stale entry → 直接重新 digest
  - stale symbol → 找到引用它的 entries，重新 digest
- [x] Card 状态机：version.status 字段已定义（fresh / stale / deprecated）

### Phase 5：Task Workspace ✅ 已完成

- [x] `repoctx task start`：创建任务目录结构
- [x] `accepted_understanding.md` 生成（LLM 驱动，失败回退到模板）
- [x] `repoctx task list`：列出所有任务工作区
- [x] `repoctx task export`：导出统一上下文 markdown
- [x] `repoctx task status`：查看任务状态与文件列表
- [x] `repoctx task validate`：检查 diff 是否违背 out_of_scope / frozen_assumptions
- [x] 测试：20 个测试全部通过

### Phase 6：Guards

- [ ] `repoctx structure-check`：基于语义记忆检查新代码结构
- [ ] `repoctx test-impact`：基于语义记忆分析测试影响
- [ ] `repoctx legacy-check`：基于 protected semantic entity 检查

### Phase 7：Experiment Agent

- [ ] `repoctx exp init/check/run/summarize/diagnose`
- [ ] 双轨诊断实现

---

## 7. 技术风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| import 解析复杂（相对 import、星号 import、动态 import） | 调用链追踪遗漏 | 第一版只处理 `import X`、`from X import Y`、`from X import Y as Z` 和简单相对导入，其他标记为 unresolved |
| 模块路径到文件路径映射错误 | 追踪不到目标函数 | 尝试 `.py` 和 `__init__.py` 两种后缀，都找不到则标记为 external |
| 类方法调用解析困难 | 遗漏 self/cls 调用链 | 第一版跳过类方法调用（标记为 unresolved），聚焦顶层函数调用链 |
| 循环调用导致无限递归 | 程序卡死 | visited set 按 `file::symbol` 去重，深度限制默认 3 |
| LLM 调用成本高、延迟大 | digest-entry 执行慢 | 只对深度 <= 2 的函数生成完整 card；深层函数只提取签名和调用关系 |
| 旧代码未完全清理 | 包导入冲突 | 旧 scanner/ 目录保留但不再被 cli.py 导入，后续统一迁移到 `_legacy/` |

---

## 8. 代码库当前状态

### 8.1 保留的旧组件

| 文件 | 说明 |
|------|------|
| `src/repoctx/llm/` | LLMClient、PromptPipeline、TokenCounter、CallLogger — 语义描述生成依赖 |
| `src/repoctx/models/config.py` | RepoCtxConfig、ModuleDefinition — 项目配置 |
| `src/repoctx/utils/yaml_io.py` | YAML 读写工具 |
| `src/repoctx/utils/project.py` | 项目根目录发现 |
| `src/repoctx/loader.py` | 配置加载 |

### 8.2 新增组件

| 文件 | 状态 | 说明 |
|------|------|------|
| `src/repoctx/cards/models.py` | ✅ 完成 | Card 数据模型 |
| `src/repoctx/cards/__init__.py` | ✅ 完成 | 导出 |
| `src/repoctx/tracer/base.py` | ✅ 完成 | `BaseTracer` 抽象基类 + `CallNode`/`CallTree`/`TracerContext` |
| `src/repoctx/tracer/factory.py` | ✅ 完成 | 按扩展名分发 tracer（预留多语言扩展位） |
| `src/repoctx/tracer/python/import_resolver.py` | ✅ 完成 | AST import 映射解析 |
| `src/repoctx/tracer/python/call_extractor.py` | ✅ 完成 | AST `Call` 节点提取 |
| `src/repoctx/tracer/python/module_resolver.py` | ✅ 完成 | 模块路径 → 文件路径 |
| `src/repoctx/tracer/python/tracer.py` | ✅ 完成 | `PythonTracer`（继承 `BaseTracer`） |
| `src/repoctx/tracer/__init__.py` | ✅ 完成 | 空 |
| `src/repoctx/semantic_memory/__init__.py` | ✅ 完成 | 空 |
| `src/repoctx/semantic_memory/engine.py` | ✅ 完成 | SemanticDigestEngine，Entry/Symbol/ContextPack 生成与持久化 |
| `src/repoctx/semantic_memory/refresh_engine.py` | ✅ 完成 | RefreshEngine，stale 检测与 affected 增量刷新 |
| `src/repoctx/semantic_memory/prompt_builder.py` | ✅ 完成 | Entry/Symbol/ContextPack prompt 组装 |
| `src/repoctx/task_workspace/engine.py` | ✅ 完成 | TaskWorkspace，start/export/validate |
| `src/repoctx/cli.py` | ✅ 重写完成 | 新命令体系已注册，digest-entry / task / guards 占位 |
| `tests/test_tracer.py` | ✅ 完成 | 22 个测试全部通过 |

### 8.3 已删除的旧组件

| 文件 | 说明 |
|------|------|
| `src/repoctx/scanner/` 整个目录 | 旧 scan 引擎（8 个文件） |
| `src/repoctx/context_router.py` | 旧语义 context router |
| `src/repoctx/entry_context.py` | 旧入口驱动分析 |
| `src/repoctx/config.py` | 空占位文件 |
| `src/repoctx/models/protected_core.py` | 旧 protected core 模型 |
| `src/repoctx/models/capability.py` | 旧 capability 模型 |
| `src/repoctx/models/rules.py` | 旧 rules 模型 |
| `tests/test_auto_analysis.py` | 旧 auto-analysis 测试 |
| `tests/test_scanner.py` | 旧 scanner 测试 |
| `tests/test_entry_context.py` | 旧 entry_context 测试 |
| `tests/test_file_scanner.py` | 旧 file_scanner 测试 |
| `tests/test_context_router.py` | 旧 context_router 测试 |

### 8.4 测试状态

| 测试文件 | 状态 | 说明 |
|----------|------|------|
| `tests/test_cli_exists.py` | ✅ 通过 | 验证新 CLI 命令注册（18 个测试） |
| `tests/test_config_system.py` | ✅ 通过 | 配置系统测试（19 个测试） |
| `tests/test_llm_client.py` | ✅ 通过 | LLM 客户端测试（24 个测试，1 跳过） |
| `tests/test_tracer.py` | ✅ 通过 | tracer 全链路测试（22 个测试） |
| `tests/test_semantic_memory.py` | ✅ 通过 | 语义记忆引擎测试（17 个测试） |
| `tests/test_refresh_engine.py` | ✅ 通过 | 刷新引擎测试（6 个测试） |
| `tests/test_task_workspace.py` | ✅ 通过 | 任务工作区测试（20 个测试） |
| `tests/test_initialization.py` | ✅ 通过 | 初始化测试（11 个测试） |
| `tests/test_card_management.py` | ✅ 通过 | Card 管理测试（8 个测试） |
| **总计** | **141 passed, 1 skipped** | — |

---

## 9. 验收标准

### MVP 1：入口语义消化

1. `repoctx digest-entry path/to/views.py --only func_a --depth 3` 能成功运行
2. 输出包含至少一个 Entry Card、若干 Symbol Card、一个 Context Pack
3. Entry Card 的 summary 能准确描述入口函数的业务职责
4. Symbol Card 能识别深层函数的语义角色（如 "credit balance read surface"）
5. Context Pack 包含主调用链和重要陷阱提示
6. 所有 card 都包含 version 信息（code_hash, git_commit）

### MVP 2：语义记忆刷新

1. `repoctx stale` 能检测 code_hash 变化的 card
2. `repoctx refresh --affected` 能增量刷新过期 card
3. 刷新后 version 信息更新，status 变为 fresh

### MVP 3：Task Workspace

1. `repoctx task start` 能创建任务目录结构
2. `repoctx task export` 能输出统一上下文 markdown
3. `repoctx validate --task` 能检测 diff 是否违背 out_of_scope

---

## 10. 变更日志

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-05-30 | v1.0 | 初始开发计划，基于轻量 scanner + context router |
| 2026-05-31 | v2.0-rewrite | 完全推翻旧设计，重写为入口驱动的语义记忆系统 |
| 2026-05-31 | v2.1 | Phase 0-4 完成（初始化、Tracer、Card 生成器、CLI、版本化与刷新） |
| 2026-05-31 | v2.2 | Phase 5 完成（Task Workspace: start/export/validate/list/status） |
