"""Interactive CLI review for auto-discovered protected cores and capabilities."""

from __future__ import annotations

from pathlib import Path

from repoctx.models import CapabilityIndex, ProtectedCoreIndex


def _ask(prompt: str, default: str = "y") -> str:
    """Ask the user for a single-character choice."""
    try:
        response = input(f"{prompt} [{default}/n/e]: ").strip().lower()
    except EOFError:
        # Non-interactive environment (e.g. CI) — treat as default
        return default
    return response if response else default


def review_protected_cores(
    index: ProtectedCoreIndex, auto_approve: bool = False
) -> ProtectedCoreIndex:
    """Interactive review of candidate protected cores.

    Args:
        index: Auto-generated protected core index.
        auto_approve: If True, skip interaction and confirm all.

    Returns:
        Index containing only confirmed cores.
    """
    if auto_approve or not index.cores:
        return index

    confirmed: list = []
    print(f"\n{'=' * 60}")
    print("Protected Core Candidates")
    print(f"{'=' * 60}")
    print("Review each candidate. y=confirm, n=skip, e=edit description")

    for core in index.cores:
        print(f"\n  Name: {core.name}")
        print(f"  Files: {core.files}")
        print(f"  Reason: {core.description}")
        choice = _ask("  Confirm", "y")
        if choice == "e":
            new_desc = input("  New description: ").strip()
            if new_desc:
                core.description = new_desc
            confirmed.append(core)
        elif choice != "n":
            confirmed.append(core)

    print(f"\nConfirmed {len(confirmed)}/{len(index.cores)} protected cores.")
    return ProtectedCoreIndex(version="1.0", cores=confirmed)


def review_capabilities(
    index: CapabilityIndex, auto_approve: bool = False
) -> CapabilityIndex:
    """Interactive review of candidate reusable capabilities.

    Args:
        index: Auto-generated capability index.
        auto_approve: If True, skip interaction and confirm all.

    Returns:
        Index containing only confirmed capabilities.
    """
    if auto_approve or not index.capabilities:
        return index

    confirmed: list = []
    print(f"\n{'=' * 60}")
    print("Reusable Capability Candidates")
    print(f"{'=' * 60}")
    print("Review each candidate. y=confirm, n=skip, e=edit description")

    for cap in index.capabilities:
        entry = cap.entry_points[0] if cap.entry_points else None
        loc = f"{entry.file_path}:{entry.function_name}" if entry else "N/A"
        print(f"\n  Name: {cap.name}")
        print(f"  Location: {loc}")
        print(f"  Description: {cap.description}")
        choice = _ask("  Confirm", "y")
        if choice == "e":
            new_desc = input("  New description: ").strip()
            if new_desc:
                cap.description = new_desc
            confirmed.append(cap)
        elif choice != "n":
            confirmed.append(cap)

    print(f"\nConfirmed {len(confirmed)}/{len(index.capabilities)} capabilities.")
    return CapabilityIndex(version="1.0", capabilities=confirmed)


def write_review_drafts(
    protected: ProtectedCoreIndex,
    capabilities: CapabilityIndex,
    project_root: Path | None = None,
) -> None:
    """Write unconfirmed candidates to review draft files.

    These files are for human inspection only; they are NOT loaded by the app.
    """
    # This is a no-op for MVP; review drafts can be added later if needed.
    pass
