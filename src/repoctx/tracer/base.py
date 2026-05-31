"""Base abstractions for language-specific call-chain tracers.

To add support for a new language or framework:

1. Subclass `BaseTracer` and implement `trace()`.
2. Register the tracer in `tracer/factory.py` for the relevant file extensions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repoctx.cards import SymbolSource


@dataclass
class CallNode:
    """A node in the call graph."""

    symbol: str
    module_path: str | None
    source: SymbolSource
    children: list[CallNode] = field(default_factory=list)
    is_external: bool = False
    call_type: str = "function"  # function | method | unknown

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "module_path": self.module_path,
            "source": self.source.model_dump(),
            "children": [c.to_dict() for c in self.children],
            "is_external": self.is_external,
            "call_type": self.call_type,
        }


@dataclass
class CallTree:
    """Result of tracing an entry point."""

    entry: CallNode
    all_nodes: list[CallNode] = field(default_factory=list)


@dataclass
class TracerContext:
    """Shared context passed to every tracer invocation.

    Contains project-wide information so that language-specific tracers
    do not need to rediscover it themselves.
    """

    project_root: Path
    framework: str = ""
    max_depth: int = 3


class BaseTracer(ABC):
    """Abstract base for all language-specific call-chain tracers.

    Subclasses must implement `trace()` and declare which file extensions
    they handle via the `extensions` class attribute.
    """

    extensions: tuple[str, ...] = ()

    def __init__(self, context: TracerContext) -> None:
        self.context = context

    @abstractmethod
    def trace(
        self,
        file_path: str,
        symbol_names: list[str] | None = None,
    ) -> CallTree:
        """Trace calls starting from the given file and symbols.

        Args:
            file_path: Relative path from project root.
            symbol_names: Specific function/class names to trace.
                If None, trace all top-level exported symbols.

        Returns:
            A CallTree rooted at the entry point(s).
        """
        raise NotImplementedError

    def accepts(self, file_path: str) -> bool:
        """Return True if this tracer can handle the given file."""
        return any(file_path.endswith(ext) for ext in self.extensions)
