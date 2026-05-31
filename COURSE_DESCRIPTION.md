0. 新产品定位
我建议把这个东西定义成：
Repo Semantic Memory & Engineering Guard
中文：

面向 AI coder 的项目语义记忆与工程守卫系统。

它不是普通 coding 插件，也不是文档生成器，而是一层放在 coder 和项目之间的控制层。
它解决四类痛点：
1. coder 每次从零理解项目，浪费 token 和时间2. coder 不同 session 对同一个项目理解不一致，互相冲突3. coder 写新代码时结构乱飘、不补测试、绕过原则4. coder 对老项目缺少敬畏，乱改底层生产资产5. 长周期实验跑完没人总结，异常结果容易被错误合理化

1. 总体架构重做
新的系统分成五个核心子系统。
A. Repo Semantic Memory   项目语义记忆层B. Task Workspace   单个需求的共享任务理解层C. Engineering Guard   新代码结构 / 原则 / 测试守卫D. Legacy Core Guardian   老代码保护与复用层E. Experiment Intelligence Agent   长周期实验记忆与诊断层
它们的关系是：
Repo Semantic Memory 是地基        ↓Task Workspace 从语义记忆里抽取当前任务理解        ↓Engineering Guard / Test Guard / Legacy Guard 基于这份理解做检查        ↓Experiment Agent 维护另一类实验语义记忆

2. A：Repo Semantic Memory
这是最核心的功能 1。
它不是轻量 scan，而是 入口驱动的语义消化系统。
2.1 它的目标
不是回答：
项目里有哪些文件？
而是回答：
从这个入口进去，代码实际做了什么？主要调用链是什么？每个深层函数在业务语义里是什么角色？哪些路径是主流程？哪些路径是异常/兼容/历史逻辑？哪些函数是公共能力？哪些地方是生产核心？这个 flow 的稳定理解是什么？
也就是说，它要把“读代码理解项目”这件事变成可复用资产。

2.2 核心输入：入口文件 / 入口函数
真实使用方式应该是：
repoctx digest-entry secondline/views/free_call_views.py
或者只关注几个入口：
repoctx digest-entry secondline/views/free_call_views.py \  --only start_free_call,check_free_call_status,free_call_callback \  --depth 4
对于 Django 项目，它会识别：
view functionclass-based viewurls.py routeserializerservicemodelutilsexternal providerCelery tasktracking eventtest file
对于实验项目，它会识别：
main scriptconfig loadertrainermodellossevaluatorloggeroutput writercheckpoint

2.3 核心输出：语义资产，而不是普通文档
它生成四类 card。
1. Entry Card
描述一个入口函数到底做什么。
card_type: entryid: entry.free_call.start_free_callsource:  file: secondline/views/free_call_views.py  symbol: start_free_callsummary: >  Starts the free call flow from the web entrypoint. It resolves user/session  state, validates request data, checks call eligibility and credit state,  creates call records, invokes the call provider, and returns call status  to the frontend.business_role:  - free call start entrypoint  - request validation boundary  - call orchestration entrymain_downstream:  - free_call.services.start_call  - credits.services.get_available_balance  - call_provider.client.start_call  - analytics.track_free_call_event

2. Path Card
描述一个入口下面的主要业务路径。
card_type: pathid: path.free_call.start.successentry: entry.free_call.start_free_callcondition: user is authenticated and eligible for free callsteps:  - parse request  - resolve account  - validate phone number  - check eligibility  - create call record  - invoke provider  - emit tracking event  - return success responsebranches:  unauthenticated:    summary: unauthenticated user is blocked or receives login-required response  insufficient_credit:    summary: user cannot start call and may be redirected to earn credits  provider_failure:    summary: call provider failed; call record should not remain in success state

3. Symbol Card
描述深层函数、service、model、util 的项目语义。
card_type: symbolid: symbol.credits.get_available_balancesource:  file: backend/credits/services.py  symbol: get_available_balancesummary: >  Public read surface for obtaining the user's available credit balance.  This should be reused by features that need balance display or eligibility  checking, instead of directly reading AccountInfo balance fields.semantic_role:  - credit balance read surface  - shared serviceside_effects: noneused_by_flows:  - free_call.start  - free_text.send  - subscription.renewal  - verification_channel.activationreuse_guidance:  use_when:    - checking eligibility    - displaying balance  avoid:    - duplicating balance calculation    - directly reading raw balance fields

4. Flow Card / Context Pack
这是给 coder 直接读的压缩上下文。
# Context Pack: Free Call Flow## Flow SummaryFree Call starts from the frontend dial action and eventually invokes the backend call start endpoint. The flow resolves auth/session state, checks call eligibility, interacts with credit services, creates call records, invokes the provider, and emits tracking events.## Main Entrypoints- `start_free_call`- `check_free_call_status`- `free_call_callback`## Main Start Path`DialPad.onDialClick`→ `useAuthGuard`→ `freeCallApi.startCall`→ `start_free_call`→ `free_call.services.start_call`→ `credits.services.get_available_balance`→ `call_provider.start_call`→ `track_free_call_event`## Important Deep Functions- `credits.services.get_available_balance`: public credit read surface.- `credits.services.consume_credits`: state mutation core, used by multiple flows.- `call_provider.start_call`: external provider side effect.## Known Pitfalls- Do not duplicate credit balance logic.- Auth timing changes usually belong near frontend action/auth guard.- Provider callback logic is separate from initial call start.- GA4 event names may be used by funnel analysis.## Related Tests- backend free call start tests- credit insufficiency tests- frontend free call E2E tests
这才是 coder 应该先读的东西。

2.4 语义资产必须版本化
每个 card 都要绑定代码版本：
version:  code_hash: "abc123"  dependency_hash: "def456"  git_commit: "9f1a2c"  generated_at: "2026-05-31T..."status: fresh
如果代码变了，它能知道：
这个 card 已经过期这个 context pack 依赖了过期 card这个 task workspace 读的是旧理解

3. 语义记忆的持续更新机制
功能 1 必须有完整更新闭环。
3.1 repoctx stale
检查哪些语义资产过期。
repoctx stale
输出：
Stale semantic assets:Changed source:- secondline/views/free_call_views.py::start_free_call- backend/free_call/services.py::check_free_call_eligibilityAffected cards:- entry.free_call.start_free_call- path.free_call.start.success- path.free_call.start.insufficient_credit- context_pack.free_callRecommended:repoctx refresh --affected

3.2 repoctx refresh
增量刷新语义资产。
repoctx refresh --affected
它不会盲目全量重写，而是分级更新：
Local refresh:  函数内部变了，只更新 symbol cardPath refresh:  调用链/分支变了，更新 path cardContext pack refresh:  flow 整体语义变了，更新 coder context pack

3.3 repoctx semantic-diff
总结代码改动带来的业务语义变化。
repoctx semantic-diff --since main
输出：
Semantic Diff: free_call.startChanged:- Auth gate moved from backend fallback path to frontend action boundary.- Backend start_call remains responsible for credit eligibility and provider invocation.- Credit deduction path unchanged.- Provider callback path unchanged.Risk:- GA4 event timing may have changed.- Existing unauthenticated backend fallback should be kept if old clients still call API directly.Recommended:- Update free_call context pack.- Add E2E test for unauthenticated dial click.
这个非常关键。它帮你知道：
这几轮改动到底改变了什么业务语义？

4. B：Task Workspace
这是为了解决多个 coder session 理解冲突。
你开始一个需求时，不应该直接把需求丢给 coder，而是创建一个 task workspace。
repoctx task start "free call login timing" \  --entry secondline/views/free_call_views.py::start_free_call
生成：
.repograph/tasks/free_call_login_timing/  task_intent.md  accepted_understanding.md  relevant_context_pack.md  change_plan.md  active_files.yaml  out_of_scope.yaml  frozen_assumptions.yaml  session_notes/  semantic_diff.md

4.1 accepted_understanding.md
这是所有 coder session 的统一理解。
# Accepted Understanding: Free Call Login Timing## Current Flow UnderstandingThe free call flow starts from the frontend dial action. The backend start_call endpoint still has fallback handling for unauthenticated users, but the intended product change is to block unauthenticated users before the backend call is triggered.## Relevant PathDialPad.onDialClick→ useAuthGuard→ freeCallApi.startCall→ start_free_call→ free_call_service→ credit check→ provider call## Intended Change ScopePrimary change should happen at the frontend action boundary or shared auth guard.## Out of Scope- credit service behavior- call provider behavior- AccountInfo model- provider callback handling## Constraints- Preserve GA4 event names.- Do not duplicate login logic in page-local state.- Add E2E coverage for unauthenticated dial click.
以后你开第二个对话，也让它先读这个。

4.2 repoctx task export
导出给 coder 的统一上下文。
repoctx task export free_call_login_timing
输出一个 markdown：
任务意图已确认理解相关 context pack主要路径已冻结假设允许修改范围不建议改的深层逻辑必要测试
注意：这里“不建议改哪里”不是主基调，只是附属。主基调还是统一理解。

4.3 repoctx validate --task
检查当前 diff 是否违背 task workspace。
repoctx validate --task free_call_login_timing
例如：
Task Validation: FailedAccepted understanding says:- credit service behavior is out of scopeCurrent diff:- modified backend/credits/services.py::consume_creditsPotential conflict:- This change expands the task scope and may affect other flows.Recommended:- revert credit service change, or- explicitly update task workspace and run impact analysis
这能防止第二个对话推翻第一个对话。

5. C：Engineering Guard
这个是功能 2，主要管新代码。
它基于 semantic memory 做检查，而不是简单 lint。
5.1 它检查什么？
1. 新文件是否放在正确模块2. 新 service 是否职责单一3. utils 是否滥用4. view/controller 是否塞业务逻辑5. frontend page 是否塞复杂状态逻辑6. 是否绕过已有 service / composable / api client7. 是否重复实现已有能力8. 是否 hardcode 临时逻辑9. 是否让新代码从第一天开始变成未来屎山

5.2 典型输出
Structure Guard WarningNew file:- backend/utils/payment_helper.pyProblem:This appears to contain billing-specific logic, but it was placed in global utils.Relevant semantic memory:- billing.services owns payment status behavior- credits.services owns credit balance behaviorSuggested location:- backend/billing/services/payment_status.pyReason:Global utils should not accumulate domain-specific business logic.

6. D：Test Impact Guard
这是功能 3。
它不是简单跑测试，而是根据语义记忆判断：
这次改动影响了哪些行为？这些行为由哪些测试保护？哪些测试应该跑？哪些测试缺失？哪些 old case 可能被破坏？
6.1 命令
repoctx test-impact --task free_call_login_timing
输出：
Affected behavior:- unauthenticated user clicks dial button- logged-in user starts call- backend fallback for unauthenticated start_call- GA4 event emission timingRecommended tests:- frontend/tests/e2e/free-call-flow.spec.ts- frontend/tests/unit/useAuthGuard.spec.ts- backend/tests/free_call/test_start_free_call.pyMissing coverage:- no test verifies unauthenticated dial click is blocked before backend call- no test verifies GA4 event name remains unchanged

7. E：Legacy Core Guardian
这是功能 3.5。
它基于 semantic memory 识别：
哪些老代码是生产资产哪些函数是 public reuse surface哪些函数是 internal core哪些 contract 不能破坏哪些底层代码被多个 flow 依赖
7.1 核心原则
老代码底层资产默认不可改。可以读，可以理解，可以复用 public interface。不能为了局部需求修改 internal core。

7.2 它不只是 protected path，而是 protected semantic entity
例如：
entity: credits.services.consume_creditsprotection_level: criticaltype: stable_core_mutationsemantic_contract:  - atomically deducts credits  - creates CreditTransaction  - raises InsufficientCreditsError on insufficient balanceused_by:  - free_call.start  - free_text.send  - subscription.renewal  - verification_channel.activationchange_policy: core_change_protocol_required
如果 coder 改了：
Legacy Core ViolationModified:- credits.services.consume_creditsWhy this is dangerous:- It is a stable core mutation function.- It is used by 4 production flows.- Changing return/exception behavior may break existing users.Required:1. explicit reason2. affected-flow analysis3. regression tests4. rollback plan5. proof that wrapper/adapter is insufficient

7.3 Reuse Surface
老代码要保护，也要复用。
capability: credit_balance_checkpublic_surfaces:  - credits.services.get_available_balance  - credits.services.has_enough_creditsdo_not_modify:  - credits.services.consume_credits  - AccountInfo raw balance fieldspreferred_extension:  - feature-specific policy wrapper
如果 coder 新写了 calculate_user_balance()，系统提醒：
Reuse IssueNew logic duplicates existing capability:- credit_balance_checkUse:- credits.services.get_available_balanceDo not:- directly read AccountInfo balance- recompute transactions- modify consume_credits for this local feature

8. F：Experiment Intelligence Agent
这是功能 4。
它相对独立，面向 research、存算一体、模型训练、NDN 实验。
8.1 它维护实验语义记忆
experiments/  runs/  summaries/  environment_notes/  failure_modes/  design_specs/  next_steps/
8.2 核心命令
repoctx exp initrepoctx exp checkrepoctx exp runrepoctx exp summarizerepoctx exp diagnose

8.3 实验前检查
repoctx exp check --config configs/lut_v9.yaml
检查：
config 是否完整output 是否覆盖旧结果git working tree 是否干净dataset 是否存在是否记录环境是否只改了一个变量是否需要 quick sanity run

8.4 实验运行与通知
repoctx exp run \  --name lut_v9_6_8_distill \  --cmd "python train.py --config configs/v9.yaml" \  --notify slack
跑完自动：
读 log读 metrics读 output比较历史 run总结优势/问题写入实验记忆发通知

8.5 双轨诊断
实验结果违反预期时，必须同时走两条路：
Track A: Scientific Interpretation如果代码是对的，为什么结果可能合理？Track B: Implementation Suspicion如果理论没错，代码哪里可能实现偏了？
比如：
Unexpected result:Method-M performance is much worse than expected.Track A:- current topology may not expose advantage- budget may not be tight enough- candidate distributions may be too similarTrack B:- fusion may be sequential rather than set-based- candidate order may affect result- ICN-adjusted hops may be leaking into utility- stale config may be usedMinimal verification:- shuffle candidate order and rerun- log marginal gain before/after fusion- run small manually inspectable case
这条非常重要，因为它防止 coder 把实现错误强行合理化成“理论就该差”。

9. 新的命令体系
现在不要再用旧的 scan/context 作为主命令。新的命令体系应该是：
Semantic Memory
repoctx digest-entry <file> [--only symbol1,symbol2] [--depth 4]repoctx stalerepoctx refresh --affectedrepoctx semantic-diff --since mainrepoctx export-context <flow-or-entry>
Task Workspace
repoctx task start "<task name>" --entry <entry>repoctx task export <task_id>repoctx task status <task_id>repoctx validate --task <task_id>
Guard
repoctx statusrepoctx structure-checkrepoctx test-impact --task <task_id>repoctx legacy-checkrepoctx commit-check
Experiment
repoctx exp initrepoctx exp check --config <config>repoctx exp run --name <name> --cmd "<cmd>"repoctx exp summarize <run_id>repoctx exp diagnose <run_id>

10. 文件结构重做
.repograph/ 应该长这样：
.repograph/  repoctx.yaml  semantic_memory/    entries/      entry.free_call.start_free_call.yaml    paths/      path.free_call.start.success.yaml      path.free_call.start.insufficient_credit.yaml    symbols/      symbol.credits.get_available_balance.yaml      symbol.credits.consume_credits.yaml    flows/      flow.free_call.yaml    context_packs/      free_call.md      credits.md      auth.md    versions/      semantic_memory_v001.yaml      semantic_memory_v002.yaml  tasks/    free_call_login_timing/      task_intent.md      accepted_understanding.md      relevant_context_pack.md      change_plan.md      active_files.yaml      out_of_scope.yaml      frozen_assumptions.yaml      session_notes/      semantic_diff.md  guards/    engineering_constitution.yaml    structure_rules.yaml    test_rules.yaml    legacy_rules.yaml  legacy/    protected_entities.yaml    reusable_capabilities.yaml    public_surfaces.yaml    core_contracts.yaml  tests/    behavior_test_map.yaml    test_impact_map.yaml  experiments/    runs/    summaries/    environment_notes/    failure_modes/    design_specs/  reports/    commit_checks/    semantic_diffs/    experiment_summaries/

11. 产品形态也要对应重做
核心产品形态：
CLI + local semantic memory + git hooks + optional daemon + optional IDE plugin
但第一版重点不是插件，而是 CLI 能真正生成和维护 semantic memory。
优先级：
Phase 1:- digest-entry- context pack- stale- refresh- task start/exportPhase 2:- validate task- semantic-diff- structure/test/legacy checksPhase 3:- experiment agentPhase 4:- daemon/watch- Slack notificationPhase 5:- VS Code/Cursor plugin

12. MVP 也要重做
旧 MVP 是错的。新的 MVP 应该是：
MVP 1：入口语义消化
只支持 Django view file。
repoctx digest-entry path/to/views.py --only func_a,func_b --depth 3
输出：
entry cardpath cardsymbol cardcontext pack
哪怕第一版追踪不完美，也必须产出“从入口往深处走的语义理解”。

MVP 2：语义记忆刷新
repoctx stalerepoctx refresh --affected
能检测：
哪个 entry 变了哪个 context pack 过期了需要刷新哪些 card

MVP 3：Task Workspace
repoctx task start ...repoctx task export ...repoctx validate --task ...
解决多个 coder session 理解不一致。

MVP 4：Legacy + Test Guard
基于 semantic memory 做：
是否改了 protected entity是否重复已有 reusable capability是否缺测试

13. 现在这套系统的核心原则
我建议把产品原则固定下来：
1. Project understanding must be persistent.   项目理解必须沉淀，而不是每个 coder session 重新生成。2. Entry points are the natural starting point.   真实屎山项目里，人通常只知道入口，所以系统必须从入口向深处消化。3. Semantic memory is the source of truth.   多个 coder session 必须读同一份语义记忆，避免理解冲突。4. Semantic memory must be versioned and refreshable.   代码改了，沉淀内容必须能检测过期并更新。5. Guards are built on semantic memory.   结构检查、测试影响、老代码保护都应该基于语义理解，而不是路径规则。6. Legacy core is production asset.   老底层代码默认不可改，只能通过 public surface 安全复用。7. Unexpected experiment results require dual-track diagnosis.   实验异常必须同时怀疑理论和怀疑实现。

14. 最终一句话
重做后的系统不是：
一个轻量 repo scanner
而是：
一个给 AI coder 使用的项目语义记忆层：它从入口函数消化代码，沉淀调用链语义，持续刷新项目理解，让不同 coder session 共享同一份稳定上下文，并基于这份语义记忆做结构、测试、老代码和实验守卫。
这个版本才真正对准你的痛点。前面那个版本确实应该推翻，不值得在上面继续补。


curl -X POST 'https://tokenhub.tencentmaas.com/v1/chat/completions' \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "deepseek-v4-flash-202605",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "你好"}
    ],
    "stream": false
  }'
