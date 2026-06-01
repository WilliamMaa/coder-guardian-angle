# repoctx

AI 代码伴侣的管控层：显式结构守卫、符号复用提示、语义记忆保持。

## 安装

```bash
pip install -e .
```

## 四大工作流

### 1. 首次设置（一次）

```bash
repoctx init                      # 创建 .repoctx.yaml + .repograph/
repoctx digest-entry copilot/view/__init__.py
cd copilot/view && repoctx digest-entry *.py
repoctx rules                     # 查看当前规则
```

> 把 `repoctx init` 加入 `rookiedata-agent` 仓库，所有同工作区成员复用同一份配置。

### 2. 日常维护

```bash
repoctx audit --all               # 快速扫描（只看错误，无建议）
repoctx audit --all -v            # 想看复用建议再加 -v
repoctx refresh --affected        # 只刷新修改过的函数卡片
repoctx refresh --prune           # 清理已删除/重命名的卡片 + 发现新函数
```

### 3. 重构

```bash
repoctx audit --dir copilot/view/ -o issues.md --deep
# --deep: LLM 给出 "helper 该搬到哪个模块" 的建议
# 读 issues.md → 改代码 → 重新 audit 验证
```

### 4. 任务协作

```bash
repoctx task start 42             # 建立 task-042/，记录工程上下文
# ... 编码 ...
repoctx task export 42 --pr       # 生成包含工程约束的 PR 描述
repoctx task validate 42          # 检查完成前是否遗漏约束
```

## 语义记忆位置配置

默认 `.repograph/` 存放在 `~/.repoctx/<project_name>/`（避免 gitignore 问题）。

如需自定义位置，在 `.repoctx.yaml` 中添加：

```yaml
project_name: rookiedata-agent
repograph_dir: ./.repograph           # 相对项目根目录
# repograph_dir: /mnt/shared/repograph # 绝对路径
```

迁移已有数据：

```bash
repoctx migrate-repograph --to ./.repograph --dry-run   # 预览
repoctx migrate-repograph --to ./.repograph             # 执行迁移
```

## 规则配置

`.repograph/guards/engineering_constitution.yaml` 定义守卫规则：

```yaml
rules:
  no_underscore_functions: {enabled: true, severity: error}
  views_only_entries:
    enabled: true
    severity: error
    view_file_patterns: ["**/views.py", "**/*_view.py", "**/*_views.py"]
```

`views_only_entries` 规则：view 文件里每个函数都必须先在 `digest-entry` 注册为 Entry，否则视为非法 helper（需搬到 utils）。

## 核心命令速查

| 命令 | 作用 |
|---|---|
| `repoctx init` | 初始化项目 |
| `repoctx rules` | 显示当前规则 |
| `repoctx digest-entry <file>` | 注册 Entry 到语义记忆 |
| `repoctx audit [--all] [-v] [--deep]` | 代码质量审计 |
| `repoctx refresh [--affected] [--prune]` | 刷新语义记忆 |
| `repoctx migrate-repograph --to <path>` | 迁移语义记忆目录 |
| `repoctx task start <id>` | 创建任务工作区 |

## License

MIT
