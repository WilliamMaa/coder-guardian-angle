# 整体产品定义

可以先叫：

```
RepoCtx Guard
```

或者更准确一点：

```
AI-assisted Development Control Plane
```

中文就是：

> 面向复杂研发项目的 AI 辅助开发控制层。
> 

它不是 coding agent，也不是 IDE 插件本身。它是站在 coder 旁边的工程控制系统，负责约束它、提醒它、审查它、记录它。

核心目标：

```
让 AI coder 在复杂项目和长周期实验中，不要乱改、不要乱飘、不要忘上下文、不要破坏老代码、不要让新代码变成未来屎山。
```

---

# 四个核心功能

## 功能 1：Repo Knowledge Graph / Context Router

这是地基。

它解决的问题是：

```
新开一个对话，coder 不知道项目结构。
AGENTS.md / cursor.md 太短，描述不了复杂项目。
coder 经常读错文件、漏掉关键模块、误解业务流。
```

功能 1 要做的是：

```
把代码库整理成知识图谱，然后给 coder 生成最小但足够准确的上下文。
```

它应该包含：

```
模块图
文件归属
API flow
frontend-backend 关系
service / utils / model / task 的职责
核心数据流
关键业务 flow
可复用能力
危险老代码
测试映射
```

它不是生成一份超长文档，而是做一个 **Context Router**。

比如你说：

```
我要改 free call 登录流程
```

它应该自动找出：

```
相关模块：
- free_call_web_flow
- auth
- credits
- GA4 tracking

关键文件：
- frontend/pages/free-call.vue
- frontend/composables/useAuthGuard.ts
- backend/freecall/views.py
- backend/credits/services.py

风险：
- 不要改 GA4 event name
- 不要绕过 auth guard
- 不要直接改 credits core
- 需要 Playwright E2E
```

最后给 coder 一个 1500-3000 token 的上下文，而不是让它自己瞎翻全库。

---

## 功能 2：Engineering Principle / Structure Guard

这个是限制新代码的。

它解决的问题是：

```
coder 写着写着就忘了开发原则。
新 API / service / utils 从第一天开始就写烂。
文件结构乱飘。
业务逻辑被塞进 view / component / utils。
它为了完成任务，会绕过你的架构原则。
```

这个模块要做的是：

```
持续检查新代码是否符合你的开发原则、架构规则和文件结构规范。
```

它应该检查：

```
service 是否职责单一
view/controller 是否塞了业务逻辑
utils 是否被滥用
common 是否被乱塞
frontend 是否绕过 API client
Django app 是否放错层级
新文件是否应该属于已有模块
是否重复实现已有能力
是否 hardcode 临时逻辑
是否引入未来屎山风险
```

比如 coder 新增：

```
backend/utils/payment_helper.py
```

系统应该提醒：

```
这个文件看起来是 billing-specific logic，不应该放进全局 utils。
已有 billing/services.py 拥有这个 domain。
建议移动到 billing/services/payment_status.py。
```

这个模块本质是：

> 新代码从诞生第一天就要被塑形，不要等它变成老代码以后再痛苦。
> 

---

## 功能 3：Test Impact & Regression Guard

这个是行为保护。

它解决的问题是：

```
coder 改了业务逻辑但不补测试。
前端 flow 改了但没有 E2E。
API 改了但没有 contract check。
旧 case 有没有被 break 根本没人知道。
```

它不应该只是跑一个 `pytest`，而是要分析：

```
这次改动影响了哪些模块？
应该跑哪些测试？
有没有测试缺口？
是否改了核心行为但没有补测试？
旧 case 可能在哪里炸？
```

比如改了：

```
credits/services.py
```

它应该自动说：

```
需要跑：
- test_credit_balance
- test_free_call_credit_check
- test_subscription_renewal
- test_verification_channel_activation

缺失测试：
- paid channel expiration with insufficient credits
- auto recharge failure case
```

前端也一样。改了 free call flow，就应该要求：

```
useAuthGuard unit test
free-call-flow Playwright test
GA4 event firing order test
```

这个功能的本质是：

> 任何行为变化都必须有保护，不能让 coder 裸奔。
> 

---

## 功能 3.5：Legacy Core Guardian

这是你刚才说的最核心痛点之一。

它解决的问题是：

```
老项目底层代码是生产资产。
coder 不知道哪些地方不能动。
它会为了一个新需求，顺手改底层函数、老 service、公共 util、API contract。
改一行可能影响几万个用户。
```

这个模块必须非常硬。

原则是：

```
老代码底层资产默认不可改。
可以读，可以理解，可以复用 public interface。
但不能为了局部需求乱改内部实现。
```

它要维护两个索引：

### 1. Protected Core Index

记录哪些东西不能乱动：

```
AccountInfo
auth/session/login
credits
billing/subscription
payment
legacy API
analytics events
queue consumer
scheduled job
shared API client
global utils
```

如果 coder 改了，就 block：

```
Commit blocked.

Modified protected core:
- backend/credits/services.py

Reason:
This file is used by free_call, free_text, subscription, verification_channel.

Required:
1. explain why core change is necessary
2. prove wrapper/adapter is not enough
3. list affected flows
4. add regression tests
5. provide rollback plan
```

### 2. Reusable Capability Index

老代码不能乱改，但要复用。

所以系统要总结：

```
已有 credit check 怎么用
已有 auth guard 怎么用
已有 billing transition 怎么用
已有 analytics tracking 怎么用
已有 API client 怎么用
已有 validation / policy 怎么用
```

然后提醒 coder：

```
你要做 balance check。
项目里已经有 credits.services.get_available_balance。
请复用它，不要新写 calculate_user_balance。
如果 verification channel 有特殊逻辑，请在 verification_channel/policies.py 里包一层，不要改 credits core。
```

这个模块的核心原则是：

```
Reuse public surface, do not mutate stable core.
```

中文就是：

> 复用老代码暴露出来的稳定能力，但不要为了复用而乱改底层。
> 

---

## 功能 4：Experiment Intelligence Agent

这个是针对 research / 模型训练 / 存算一体 / NDN 实验的。

它解决的问题是：

```
一次实验 4-5 小时甚至更久。
实验文件夹容易被 coder 搞乱。
环境配置坑很多。
跑完没人总结。
结果不符合预期时，AI 容易强行合理化。
历史失败经验没有沉淀。
下一步实验思路每次都要重新想。
```

这个模块要做的是：

```
管理长周期实验的结构、运行、监控、总结、异常诊断和下一步建议。
```

它包含：

```
实验结构保护
环境 setup memory
preflight check
runtime monitor
post-run summary
dual-track diagnosis
failure mode memory
next-step generator
Slack / Email notification
```

最重要的是 **双轨诊断**。

实验结果违反预期时，不能只说：

```
可能是你的理论不对。
```

它必须同时走两条路：

```
Track A: Scientific Interpretation
如果代码是对的，为什么结果可能合理？

Track B: Implementation Suspicion
如果理论没错，代码哪里可能实现偏了？
```

比如你那个粒子滤波 sequential fusion 问题，系统应该提醒：

```
结果差不一定说明方法差。
可能是 fusion 实现和设计不一致。

检查：
- fusion 是否 order-dependent
- 是否 sequential update 了 belief
- 是否应该 set-level aggregation
- candidate order shuffle 后结果是否变化
```

这条非常关键，因为 AI coder 很容易把实现错误合理化成“实验本来就该差”。

---

# 它们之间的关系

这四个模块不是散的，而是一套闭环。

```
功能 1：告诉 coder 应该看什么、用什么、别碰什么
功能 2：约束新代码不要写烂、不要乱放
功能 3：约束行为变化必须有测试保护
功能 3.5：保护老代码底层资产，同时引导安全复用
功能 4：管理长周期实验，记录结果，防止错误解释
```

如果画成流程，就是：

```
用户提出任务
  ↓
功能 1 生成任务上下文
  ↓
coder 开始修改
  ↓
功能 2 持续检查结构和原则
  ↓
功能 3 检查测试和 regression 风险
  ↓
功能 3.5 检查是否碰了老核心
  ↓
commit 前统一 gate
  ↓
如果是实验任务，功能 4 接管运行、总结、诊断、通知
```

---

# 最小 MVP 应该怎么做

我觉得你现在不要一口气做全套。先做一个非常实际的 CLI。

可以叫：

```
repoctx
```

第一版只做 6 个命令。

---

## 1. `repoctx scan`

扫描项目，生成知识图谱基础文件。

```
repoctx scan
```

生成：

```
.repograph/
  index.json
  modules/
  entities/
  edges/
  rules/
  protected_core.yaml
  reusable_capabilities.yaml
```

---

## 2. `repoctx context "<task>"`

根据任务生成 coder 上下文。

```
repoctx context"change free call login timing"
```

输出：

```
相关模块
关键文件
可复用能力
禁止修改的 core
需要注意的开发原则
建议测试
```

---

## 3. `repoctx status`

持续查看当前 working tree 健康度。

```
repoctx status
```

输出：

```
改了多少文件
改了多少行
涉及几个模块
是否跨前后端
是否没改测试
是否碰了 protected core
是否该 commit
```

---

## 4. `repoctx commit-check`

commit 前统一检查。

```
repoctx commit-check
```

检查：

```
改动粒度是否过大
新代码结构是否合理
是否违反开发原则
是否缺测试
是否可能 break old case
是否修改老核心
是否重复造轮子
```

---

## 5. `repoctx test-impact`

专门分析测试影响。

```
repoctx test-impact
```

输出：

```
建议跑哪些测试
缺哪些测试
哪些 old case 可能受影响
```

---

## 6. `repoctx exp run / summarize`

实验模块第一版。

```
repoctx exp run--name lut_v9--cmd"python train.py ..."
repoctx exp summarize--run lut_v9
```

跑完生成：

```
实验摘要
指标变化
异常
双轨诊断
下一步建议
写入 experiment memory
通知 Slack
```

---

# 第一版最关键的几个配置文件

你可以先不做复杂数据库，先用 YAML / JSON 就够。

```
.repoctx.yaml
.repograph/modules/*.json
.repograph/rules/project_rules.yaml
.repograph/rules/engineering_constitution.yaml
.repograph/protected_core.yaml
.repograph/reusable_capabilities.yaml
.repograph/experiments/
```

尤其是这两个非常重要：

```
protected_core.yaml
reusable_capabilities.yaml
```

你可以先手写 20 个最危险的老代码、20 个最常用的可复用能力。这个会立刻产生价值。

---

# 这个系统的工程宪法可以先定成这些

```
1. AI must not work without project context.
   AI 不能在不知道项目上下文的情况下乱改。

2. New code must not become future legacy debt.
   新代码不能从诞生开始就变成未来屎山。

3. Every behavior change needs protection.
   任何行为变化都必须有测试、影响分析或明确确认。

4. Legacy core is production asset, not editable code.
   老项目底层代码是生产资产，不是普通可编辑实现。

5. Reuse public surfaces, not internal guts.
   复用已有公开能力，不要为了局部需求修改底层实现。

6. Large changes must be split.
   改动过大必须提醒 commit / split。

7. Unexpected experimental results must not be automatically rationalized.
   实验结果违反预期时，必须同时怀疑理论和怀疑实现。
```

这几条已经很完整了。


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
