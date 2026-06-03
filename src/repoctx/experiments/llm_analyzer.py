"""LLM-driven deep analysis of a completed experiment run."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from repoctx.models.experiment import (
    ExperimentContract,
    ExtractedMetric,
    LightAnalysis,
    LLMAnalysis,
    ResultFile,
)

logger = logging.getLogger("repoctx.experiments.llm_analyzer")

# Safety limits
_MAX_NOHUP_LINES = 200
_MAX_RESULT_FILE_BYTES = 500 * 1024  # 500 KB


class LLMExperimentAnalyzer:
    """Analyze experiment results with LLM after the process exits."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.pipeline = self._get_pipeline()

    def _get_pipeline(self) -> Any:
        """Re-use the SemanticDigestEngine pipeline."""
        from repoctx.semantic_memory.engine import SemanticDigestEngine

        engine = SemanticDigestEngine(self.project_root)
        return engine.pipeline

    def analyze(
        self,
        nohup_text: str,
        result_files: list[ResultFile],
        contract: ExperimentContract,
        light_result: LightAnalysis,
    ) -> LLMAnalysis:
        """Build prompt and ask LLM for a deep analysis."""
        prompt = self._build_prompt(nohup_text, result_files, contract, light_result)

        raw = self.pipeline.client.chat_completion_with_retry(
            [{"role": "user", "content": prompt}]
        )

        # Best-effort parsing: treat the LLM response as the summary
        # Future: could attempt structured JSON extraction
        return LLMAnalysis(
            status=light_result.status,
            summary=raw.strip(),
            extracted_metrics=[],
            issues=[],
            recommendations=[],
        )

    def _build_prompt(
        self,
        nohup_text: str,
        result_files: list[ResultFile],
        contract: ExperimentContract,
        light_result: LightAnalysis,
    ) -> str:
        """Assemble the analysis prompt."""
        # Trim nohup to last N lines
        nohup_lines = nohup_text.splitlines()
        trimmed_nohup = "\n".join(nohup_lines[-_MAX_NOHUP_LINES:])

        parts: list[str] = [
            f"Experiment contract purpose: {contract.contract.purpose}",
            f"Expected behavior: {contract.contract.expected_behavior.model_dump(mode='json')}",
            "",
            f"Light analysis status: {light_result.status}",
            f"Light analysis hints: {light_result.hints}",
            "",
            f"Nohup output (last {_MAX_NOHUP_LINES} lines):",
            "```",
            trimmed_nohup,
            "```",
        ]

        for rf in result_files:
            p = Path(rf.path)
            content = ""
            if p.exists():
                try:
                    size = p.stat().st_size
                    if size > _MAX_RESULT_FILE_BYTES:
                        with open(p, "rb") as f:
                            f.seek(-_MAX_RESULT_FILE_BYTES, 2)
                            content = f.read().decode("utf-8", errors="ignore")
                        content += "\n... (truncated)"
                    else:
                        content = p.read_text(encoding="utf-8", errors="ignore")
                except OSError as e:
                    content = f"[Failed to read: {e}]"
            else:
                content = "[File not found]"

            parts.extend([
                "",
                f"Result file {rf.path} (source: {rf.source}):",
                "```",
                content,
                "```",
            ])

        parts.extend([
            "",
            "请分析：",
            "1. 实验完成了吗？状态是什么？",
            "2. 如果有结果，关键指标是什么？",
            "3. 和预期行为对比，是否达标？",
            "4. 有没有异常、错误或警告？",
            "5. 给出下一步建议。",
            "如果结果文件里没有可分析的内容，直接说'无有效结果可分析'。",
        ])

        return "\n".join(parts)
