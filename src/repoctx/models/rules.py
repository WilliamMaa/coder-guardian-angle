"""Data models for project rules and engineering constitution."""

from pydantic import BaseModel, Field


class FileStructureRule(BaseModel):
    """Rule defining allowed/forbidden file types in a directory pattern."""

    pattern: str = Field(..., description="Glob pattern for directory or path")
    allowed_types: list[str] = Field(default_factory=list, description="Allowed file types/patterns")
    forbidden_types: list[str] = Field(
        default_factory=list,
        description="Forbidden file types/patterns",
    )
    message: str = Field(default="", description="Violation message")
    severity: str = Field(default="warning", description="blocker, warning, or suggestion")


class NamingConvention(BaseModel):
    """Naming convention rule."""

    scope: str = Field(..., description="Scope: file, function, class, variable, module")
    pattern: str = Field(..., description="Regex or glob pattern")
    description: str = Field(..., description="Human-readable description")
    severity: str = Field(default="warning", description="blocker, warning, or suggestion")


class ModuleBoundary(BaseModel):
    """Module boundary rule."""

    module_id: str = Field(..., description="Module identifier")
    public_interfaces: list[str] = Field(
        default_factory=list,
        description="Glob patterns for public interface files",
    )
    private_internals: list[str] = Field(
        default_factory=list,
        description="Glob patterns for private internal files",
    )


class CrossModuleRule(BaseModel):
    """Cross-module interaction rule."""

    source: str = Field(..., description="Source module pattern")
    target: str = Field(..., description="Target module pattern")
    allowed: bool = Field(default=True, description="Whether interaction is allowed")
    message: str = Field(default="", description="Violation message")
    severity: str = Field(default="blocker", description="blocker, warning, or suggestion")


class ProjectRules(BaseModel):
    """Root model for project_rules.yaml."""

    file_structure: list[FileStructureRule] = Field(default_factory=list)
    naming_conventions: list[NamingConvention] = Field(default_factory=list)
    module_boundaries: list[ModuleBoundary] = Field(default_factory=list)
    cross_module_rules: list[CrossModuleRule] = Field(default_factory=list)


class Check(BaseModel):
    """A single executable check item for an engineering principle."""

    name: str = Field(..., description="Check name")
    description: str = Field(..., description="What this check does")
    severity: str = Field(default="warning", description="blocker, warning, or suggestion")
    applies_to: list[str] = Field(
        default_factory=list,
        description="File types or module types this check applies to",
    )


class Principle(BaseModel):
    """An engineering constitution principle with executable checks."""

    id: str = Field(..., description="Principle ID, e.g. EC-1")
    statement: str = Field(..., description="Human-readable principle statement")
    checks: list[Check] = Field(default_factory=list, description="Executable checks")


class EngineeringConstitution(BaseModel):
    """Root model for engineering_constitution.yaml."""

    principles: list[Principle] = Field(default_factory=list)
