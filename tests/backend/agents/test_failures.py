from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from backend.agents.errors import InvalidModelOutputError
from backend.agents.schemas.brand_spec import BrandSpec
from backend.agents.testing import InMemoryArtifactWriter, InMemoryInvocationRecorder
from backend.agents.workflow import build_brand_workflow
from backend.providers.models.base import ModelCapability
from backend.providers.models.fake import FakeImageModelProvider, FakeTextModelProvider


def _complete_spec() -> BrandSpec:
    return BrandSpec(
        project_name="测试品牌",
        industry="消费品",
        brand_background="为城市用户提供可靠的日常产品。",
        target_audiences=["城市消费者"],
        style_keywords=["现代", "清晰", "可靠"],
    )


def _invoke(workflow, thread_id: str = "failure-thread"):
    return workflow.invoke(
        {
            "project_id": f"project-{thread_id}",
            "brand_spec": _complete_spec().model_dump(mode="json"),
            "status": "INTAKE",
        },
        config={"configurable": {"thread_id": thread_id}},
    )


class InvalidThenValidTextProvider:
    def __init__(self) -> None:
        self.base = FakeTextModelProvider()
        self.repair_calls = 0

    def generate_structured(self, request):
        if request.capability is not ModelCapability.DIRECTIONS:
            return self.base.generate_structured(request)
        if request.prompt_version.endswith("-repair"):
            self.repair_calls += 1
            return self.base.generate_structured(request)
        result = self.base.generate_structured(request)
        result.content_json["directions"] = result.content_json["directions"][:2]
        return result


class AlwaysInvalidDirectionsProvider:
    def __init__(self) -> None:
        self.base = FakeTextModelProvider()

    def generate_structured(self, request):
        if request.capability is ModelCapability.DIRECTIONS:
            result = self.base.generate_structured(request)
            result.content_json = {}
            return result
        return self.base.generate_structured(request)


class FailingSecondImageProvider:
    def __init__(self) -> None:
        self.base = FakeImageModelProvider()
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("simulated image provider outage")
        return self.base.generate(request)


def test_invalid_structured_output_is_repaired_once() -> None:
    provider = InvalidThenValidTextProvider()
    workflow = build_brand_workflow(
        text_provider=provider,
        image_provider=FakeImageModelProvider(),
        artifact_writer=InMemoryArtifactWriter(),
        invocation_recorder=InMemoryInvocationRecorder(),
        checkpointer=InMemorySaver(),
    )

    result = _invoke(workflow, "repair")

    assert provider.repair_calls == 1
    assert result["status"] == "WAITING_USER"
    assert len(result["direction_output"]["directions"]) == 3


def test_invalid_structured_output_fails_after_one_repair() -> None:
    workflow = build_brand_workflow(
        text_provider=AlwaysInvalidDirectionsProvider(),
        image_provider=FakeImageModelProvider(),
        artifact_writer=InMemoryArtifactWriter(),
        invocation_recorder=InMemoryInvocationRecorder(),
        checkpointer=InMemorySaver(),
    )

    with pytest.raises(InvalidModelOutputError, match="after one repair"):
        _invoke(workflow, "invalid")


def test_partial_image_batch_is_discarded() -> None:
    artifact_writer = InMemoryArtifactWriter()
    workflow = build_brand_workflow(
        text_provider=FakeTextModelProvider(),
        image_provider=FailingSecondImageProvider(),
        artifact_writer=artifact_writer,
        invocation_recorder=InMemoryInvocationRecorder(),
        checkpointer=InMemorySaver(),
    )

    with pytest.raises(RuntimeError, match="simulated image provider outage"):
        _invoke(workflow, "image-failure")

    assert artifact_writer.items == {}
