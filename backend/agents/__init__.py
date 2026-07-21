"""Brand Agent Studio agent contracts and workflow."""

from typing import TYPE_CHECKING

__all__ = ["BrandWorkflowState", "build_brand_workflow"]

if TYPE_CHECKING:
    from backend.agents.workflow import BrandWorkflowState, build_brand_workflow


def __getattr__(name: str):
    if name in __all__:
        from backend.agents import workflow

        return getattr(workflow, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
