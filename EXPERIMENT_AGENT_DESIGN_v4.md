# Experiment Intelligence Agent 设计方案 v4（最终版）

> 基于用户反馈的最终定稿。核心：`exp run` 接受命令 → nohup 启动 → 轻量监控 → 事后 LLM 分析。

---

## 1. 工作流（最终版）

### Step 1：一次性的契约生成

```bash
repoctx digest-entry experiments/lut_coco_v10.py --depth 3
repoctx exp init --entry experiments/lut_coco_v10.py --name lut_coco
repoctx exp edit lut_coco   # 交互式补全，也可以直接改 yaml
```

### Step 2：运行实验（核心命令）

```bash
repoctx exp run "python experiments/lut_coco_v10.py --phase 1 --epoch 50" \
  --contract lut_coco \
  --notify
```

系统行为：
1. **解析命令**
   - 提取 `output_dir` 等参数（从命令字符串或契约推断）
   - 如果没有 `--output_dir`，用契约中的 default 或当前目录

2. **nohup 启动**
   ```bash
   nohup python experiments/lut_coco_v10.py --phase 1 --epoch 50 \
     > .repograph/experiments/nohup_logs/lut_coco.20260601_143022.nohup 2>&1 &
   ```
   - nohup 输出重定向到 `.repograph/experiments/nohup_logs/`（不在项目根目录留垃圾）
   - 记录 PID

3. **启动监控进程**（后台线程，非阻塞）
   ```python
   monitor = ExperimentMonitor(
       contract=contract,
       nohup_path=nohup_path,
       pid=pid,
       output_dir=output_dir,
   )
   monitor.start()  # 非阻塞，后台运行
   ```

   监控进程的行为：
   - 每秒检查一次进程是否存活
   - 进程退出后，读取 nohup 输出
   - **轻量分析 nohup**：
     - 如果 nohup 里有明确的"完成"信号（如 "Training complete"、"Done"、exit 0），标记 completed
     - 如果 nohup 里有错误（OOM、Segmentation fault、Traceback），标记 failed + 提取错误信息
     - 如果 nohup 只是 execution log（如 NDNSim 的 "Simulation started" / "Simulation ended"），标记 completed，**不硬分析**
   - **根据 nohup 线索读结果文件**：
     - 如果 nohup 里有 `"Results saved to ./results/metrics.json"`，去读那个文件
     - 如果 nohup 里有 `"Output written to ./runs/v1/final.txt"`，去读那个文件
     - 如果契约里指定了 output_files，按契约去读
     - **否则不扫 output_dir**（NDNSim 产物可能几十万文件）

4. **监控进程退出**
   - 进程结束后，监控进程再存活最多 30 秒（等文件写入完成）
   - 然后做一次 LLM 分析
   - 生成 ExperimentRun
   - 发送 Slack 通知
   - 监控进程自己退出

5. **用户视角**
   ```
   $ repoctx exp run "python experiments/lut_coco_v10.py --phase 1 --epoch 50" --contract lut_coco --notify
   
   🚀 Experiment launched: lut_coco
   PID: 18472
   Nohup log: ~/.repoctx/.../experiments/nohup_logs/lut_coco.20260601_143022.nohup
   Monitor: started (background)
   
   The experiment is running in background. You will receive a Slack notification when it completes.
   ```

   几小时后 Slack 收到：
   ```
   🧪 [lut_coco] Experiment Complete
   
   Status: ✅ Completed (PID 18472 exited with code 0)
   Duration: 2h 14m
   
   📊 Results
   • mAP@0.5: 0.781 (from ./runs/v1/results.csv)
   • Final loss: 0.028
   • Checkpoint: ./runs/v1/best.pt (420MB)
   
   ✅ All success criteria met.
   ```

### Step 3：诊断

```bash
# 默认比较最近一次成功 run
repoctx exp diagnose lut_coco

# 比较最近 5 次成功 run
repoctx exp diagnose lut_coco --compare-recent-success-num 5
```

---

## 2. 监控进程详细设计

### 2.1 生命周期

```
[User] repoctx exp run "cmd" --contract X
    ↓
[Main] nohup cmd > nohup_log 2>&1 &
       记录 PID
    ↓
[Main] 启动 MonitorThread（daemon）
    ↓
[Main] 立即返回给用户（"已后台启动"）
    ↓
[MonitorThread] loop:
    每秒检查 os.kill(pid, 0)
    如果进程存活：继续 loop
    如果进程退出：
        等 30s（等文件 flush）
        读取 nohup_log
        轻量分析
        按需读取结果文件
        LLM 深度分析
        生成 ExperimentRun
        发 Slack
        线程退出
```

### 2.2 轻量分析规则（监控进程自己做，不调用 LLM）

```python
def light_analyze(nohup_text: str, contract: dict) -> dict:
    """快速判断实验状态，不调用 LLM。"""
    result = {"status": "unknown", "hints": []}
    
    # 1. 检查错误信号
    if "CUDA out of memory" in nohup_text or "OOM" in nohup_text:
        result["status"] = "oom"
        result["hints"].append("CUDA OOM detected")
    elif "Segmentation fault" in nohup_text:
        result["status"] = "crashed"
        result["hints"].append("Segmentation fault")
    elif "Traceback (most recent call last)" in nohup_text:
        result["status"] = "failed"
        result["hints"].append("Python exception")
    elif "Killed" in nohup_text:
        result["status"] = "killed"
        result["hints"].append("Process killed (likely OOM by system)")
    
    # 2. 检查完成信号
    elif any(sig in nohup_text for sig in ["Done", "Complete", "Finished", "Simulation ended"]):
        result["status"] = "completed"
    
    # 3. 从 nohup 中提取结果文件线索
    import re
    file_refs = re.findall(r'(?:saved|written|output|results?)\s+(?:to|at|in)\s+["\']?([^\s"\']+)', nohup_text, re.I)
    if file_refs:
        result["hints"].extend(f"Result file referenced: {f}" for f in file_refs)
    
    return result
```

### 2.3 按需读取结果文件

```python
def read_results(light_result: dict, contract: dict, output_dir: Path) -> dict:
    """基于线索读取结果文件，不扫整个目录。"""
    files_read = []
    
    # 优先级 1：nohup 里明确提到的文件
    for hint in light_result.get("hints", []):
        if hint.startswith("Result file referenced:"):
            path = hint.replace("Result file referenced: ", "").strip()
            full_path = output_dir / path if not Path(path).is_absolute() else Path(path)
            if full_path.exists():
                files_read.append({"path": full_path, "source": "nohup_reference"})
    
    # 优先级 2：契约中指定的 output_files
    for of in contract.get("output_files", []):
        pattern = of["pattern"].format(output_dir=output_dir)
        path = Path(pattern)
        if path.exists():
            files_read.append({"path": path, "source": "contract"})
    
    # 优先级 3：如果以上都没有，且 output_dir 存在，只读一层（不递归）
    if not files_read and output_dir.exists():
        for f in output_dir.iterdir():
            if f.is_file() and f.suffix in [".csv", ".json", ".txt", ".log", ".yaml", ".pt", ".pth"]:
                files_read.append({"path": f, "source": "output_dir_scan"})
            if len(files_read) > 10:  # 上限，防止 NDNSim 产物爆炸
                break
    
    return {"files": files_read}
```

### 2.4 LLM 分析（进程退出后做一次）

```python
def llm_analyze(nohup_text: str, result_files: list, contract: dict, light_result: dict) -> dict:
    """进程退出后，用 LLM 做一次深度分析。"""
    
    # 构建 prompt
    prompt_parts = [
        f"实验契约：{contract['purpose']}",
        f"预期行为：{contract.get('expected_behavior', {})}",
        "",
        f"nohup 输出（最后 200 行）：",
        "```",
        "\n".join(nohup_text.splitlines()[-200:]),
        "```",
    ]
    
    for f in result_files:
        content = f["path"].read_text(encoding="utf-8", errors="ignore")
        if len(content) > 5000:
            content = content[:5000] + "\n... (truncated)"
        prompt_parts.extend([
            "",
            f"结果文件 {f['path']}：",
            "```",
            content,
            "```",
        ])
    
    prompt_parts.extend([
        "",
        "请分析：",
        "1. 实验完成了吗？状态是什么？",
        "2. 如果有结果，关键指标是什么？",
        "3. 和预期行为对比，是否达标？",
        "4. 有没有异常、错误或警告？",
        "5. 给出下一步建议。",
        "如果结果文件里没有可分析的内容，直接说'无有效结果可分析'。",
    ])
    
    return pipeline.client.chat_completion_with_retry(
        [{"role": "user", "content": "\n".join(prompt_parts)}]
    )
```

---

## 3. Slack 通知（分多条）

```python
def send_slack_notification(webhook_url: str, report: dict) -> None:
    """报告太长就分多条发送。"""
    blocks = build_slack_blocks(report)  # 转成 Slack Block Kit 格式
    
    # Slack 单条消息上限 ~3000 字符
    MAX_LEN = 2800
    messages = []
    current = []
    current_len = 0
    
    for block in blocks:
        block_text = block.get("text", "")
        if current_len + len(block_text) > MAX_LEN and current:
            messages.append(current)
            current = [block]
            current_len = len(block_text)
        else:
            current.append(block)
            current_len += len(block_text)
    
    if current:
        messages.append(current)
    
    for i, msg_blocks in enumerate(messages):
        payload = {
            "text": f"Experiment Report ({i+1}/{len(messages)})",
            "blocks": msg_blocks,
        }
        requests.post(webhook_url, json=payload)
```

---

## 4. 数据模型 v4（精简）

### ExperimentContract

```yaml
id: lut_coco
entry_file: experiments/lut_coco_v10.py
entry_symbol: main
status: reviewed

contract:
  purpose: "LUT-based COCO detection training"
  
  output_files:
    - pattern: "{output_dir}/results.csv"
      note: "训练指标"
    - pattern: "{output_dir}/best.pt"
      note: "模型权重"
  
  log_destinations:
    - type: nohup
      path: "~/.repoctx/.../nohup_logs/"
  
  cli_args:
    - name: --phase
    - name: --epoch
    - name: --output_dir
      default: "./outputs"
  
  expected_behavior:
    success_criteria:
      - "mAP > 0.75"
    failure_signs:
      - "OOM"
      - "NaN"
```

### ExperimentRun

```yaml
id: lut_coco.20260601_143022
contract_id: lut_coco

# 执行信息
cmd: "python experiments/lut_coco_v10.py --phase 1 --epoch 50"
pid: 18472
nohup_path: ~/.repoctx/.../nohup_logs/lut_coco.20260601_143022.nohup

# 轻量分析结果
light_analysis:
  status: completed
  hints: ["Simulation ended"]

# LLM 分析结果（核心）
llm_analysis:
  status: completed
  summary: "训练正常完成，50 epochs，mAP=0.781"
  extracted_metrics:
    - {name: mAP, value: 0.781, source: "./outputs/results.csv"}
    - {name: final_loss, value: 0.028}
  issues: []
  recommendations:
    - "结果达标，无需调整"

# 读取的文件
result_files:
  - path: ./outputs/results.csv
    source: contract
  - path: ./outputs/best.pt
    source: contract

duration_seconds: 8040
```

---

## 5. 命令汇总

```bash
# 生成契约
repoctx exp init --entry experiments/lut_coco_v10.py --name lut_coco
repoctx exp edit lut_coco

# 运行实验（核心）
repoctx exp run "python experiments/lut_coco_v10.py --phase 1 --epoch 50" \
  --contract lut_coco \
  --notify

# 诊断
repoctx exp diagnose lut_coco                    # 对比最近一次
repoctx exp diagnose lut_coco --compare-recent-success-num 5

# 历史
repoctx exp history lut_coco

# 查看运行中的实验
repoctx exp ps                                   # 列出活跃监控进程
repoctx exp logs lut_coco                        # tail nohup 输出
```

---

## 6. 配置

`.repoctx.yaml`：

```yaml
project_name: copilot-backend

notifications:
  slack:
    webhook_url: "${SLACK_WEBHOOK_URL}"  # 从环境变量读取
    on_events: ["completed", "failed", "crashed", "oom"]
    max_blocks_per_message: 10

experiments:
  nohup_log_dir: "~/.repoctx/copilot-backend/.repograph/experiments/nohup_logs"
  monitor_poll_interval: 5  # 秒
  post_exit_wait: 30        # 进程退出后等多久再分析（等文件 flush）
  max_nohup_lines_for_llm: 200
  max_result_file_size_kb: 500
```

---

## 7. 实现顺序

1. **契约系统**：`exp init` + `exp edit` + AST 提取器
2. **`exp run` + MonitorThread**：nohup 启动 + 进程监控 + 轻量分析
3. **LLM 分析**：进程退出后的深度分析 + ExperimentRun 生成
4. **Slack 通知**：分多条发送
5. **诊断系统**：`exp diagnose` + 历史对比
6. **`exp ps` / `exp logs`**：查看运行中实验
