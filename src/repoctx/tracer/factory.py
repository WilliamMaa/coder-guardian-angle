"""Tracer factory — select the right language-specific tracer for a file."""

from __future__ import annotations

from repoctx.tracer.base import BaseTracer, TracerContext
from repoctx.tracer.python import PythonTracer

# Registry of tracers by file extension.
# To add a new language, import its tracer class here and register it.
_TRACER_CLASSES: list[type[BaseTracer]] = [
    PythonTracer,
    # Future: JavaScriptTracer, TypeScriptTracer, VueTracer, GoTracer, etc.
]


def get_tracer(file_path: str, context: TracerContext) -> BaseTracer:
    """Return a tracer instance capable of handling *file_path*.

    Args:
        file_path: Relative file path from project root.
        context: Shared tracer context.

    Returns:
        A ``BaseTracer`` subclass instance.

    Raises:
        ValueError: If no registered tracer can handle the file extension.
    """
    for tracer_cls in _TRACER_CLASSES:
        # Check via class-level extensions
        if any(file_path.endswith(ext) for ext in tracer_cls.extensions):
            return tracer_cls(context)

    raise ValueError(
        f"No tracer registered for file: {file_path}. "
        f"Supported extensions: {sum((list(t.extensions) for t in _TRACER_CLASSES), [])}"
    )
