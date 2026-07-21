from __future__ import annotations

import threading
from uuid import NAMESPACE_URL, uuid5

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backend.agents.schemas.brand_spec import BrandSpec
from backend.agents.schemas.common import PaletteColor
from backend.agents.schemas.directions import Direction, DirectionOutput, TypographyDirection
from backend.agents.schemas.intake import IntakeOutput
from backend.agents.schemas.ip import IPOutput
from backend.agents.schemas.logo import LogoDraft, LogoOutput
from backend.agents.testing import InMemoryArtifactWriter, InMemoryInvocationRecorder
from backend.agents.workflow import build_brand_workflow, build_short_logo_image_prompt
from backend.providers.models.base import GeneratedImage, ImageGenerationRequest
from backend.providers.models.errors import ProviderError, ProviderErrorCode
from backend.providers.models.fake import FakeImageModelProvider, FakeTextModelProvider


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _version(stage: str):
    return uuid5(NAMESPACE_URL, f"test-version:{stage}")


def _resume(workflow, config: dict, payload: dict):
    return workflow.invoke(Command(resume=payload), config=config)


def _complete_spec() -> BrandSpec:
    return BrandSpec(
        project_name="云山咖啡",
        industry="精品咖啡",
        brand_background="面向城市通勤者的社区精品咖啡品牌。",
        target_audiences=["25–35 岁城市通勤者"],
        price_positioning="中高端日常消费",
        brand_personality=["可靠", "温暖"],
        style_keywords=["现代", "自然", "克制"],
        prohibited_elements=["动物形象", "大面积红色"],
    )


def test_logo_image_prompt_is_compacted_for_image_provider() -> None:
    brand_spec = _complete_spec()
    selected_direction = Direction(
        id="direction-clear",
        name="清晰秩序",
        concept="以克制网格和高留白建立可信、稳定的品牌印象。",
        keywords=["克制", "秩序", "可信"],
        palette=[
            PaletteColor(name="墨黑", hex="#111111", usage="主文字与标识"),
            PaletteColor(name="暖白", hex="#F7F3EA", usage="主背景"),
            PaletteColor(name="雾灰", hex="#B8BDC6", usage="辅助信息"),
        ],
        typography=TypographyDirection(
            heading_style="清晰现代中文标题字",
            body_style="高可读性无衬线正文字体",
        ),
        composition="稳定网格和大面积留白。",
        rationale="适合城市通勤者。",
        image_prompt="品牌方向图",
        preview_asset_id=_version("direction-asset"),
    )
    draft = LogoDraft(
        id="logo-combination",
        name="组合标识",
        rationale="兼顾完整表达和拆分使用。",
        symbolism="文字负责品牌名称，符号承载方向概念。",
        shape_language="符号与字标比例明确，横版与竖版均可延展。",
        color_strategy="采用方向色板中的主色与中性色组合。",
        image_prompt="这是一段很长的原始提示词，不应直接发送给图片模型。" * 20,
    )

    prompt = build_short_logo_image_prompt(brand_spec, selected_direction, draft)

    assert len(prompt) <= 220
    assert "组合标识 Logo" in prompt
    assert "白底居中" in prompt
    assert "扁平矢量" in prompt
    assert "不要" not in prompt
    assert "版权" not in prompt


def test_complete_information_reaches_direction_confirmation(workflow) -> None:
    result = workflow.invoke(
        {
            "project_id": "project-complete",
            "brand_spec": _complete_spec().model_dump(mode="json"),
            "status": "INTAKE",
        },
        config=_config("thread-complete"),
    )

    assert result["status"] == "WAITING_USER"
    direction_output = DirectionOutput.model_validate(result["direction_output"])
    assert len(direction_output.directions) == 3
    assert len({item.preview_asset_id for item in direction_output.directions}) == 3
    assert result["__interrupt__"][0].value["kind"] == "direction_decision"


def test_image_generation_retries_transient_provider_load(monkeypatch) -> None:
    class FlakyImageProvider:
        provider_name = "fake"
        model_name = "flaky-image-v1"

        def __init__(self) -> None:
            self.calls = 0
            self._lock = threading.Lock()

        def generate(self, request: ImageGenerationRequest) -> list[GeneratedImage]:
            with self._lock:
                self.calls += 1
                call_number = self.calls
            if call_number <= 4:
                raise ProviderError(
                    ProviderErrorCode.UNAVAILABLE,
                    "OpenAI 请求失败（HTTP 400）。 上游返回：excessive system load",
                    retryable=True,
                )
            return FakeImageModelProvider().generate(request)

    sleep_calls: list[float] = []
    monkeypatch.setattr("backend.agents.workflow.time.sleep", sleep_calls.append)
    image_provider = FlakyImageProvider()
    workflow = build_brand_workflow(
        text_provider=FakeTextModelProvider(),
        image_provider=image_provider,
        artifact_writer=InMemoryArtifactWriter(),
        invocation_recorder=InMemoryInvocationRecorder(),
        checkpointer=InMemorySaver(),
    )

    result = workflow.invoke(
        {
            "project_id": "project-retry-load",
            "brand_spec": _complete_spec().model_dump(mode="json"),
            "status": "INTAKE",
        },
        config=_config("thread-retry-load"),
    )

    assert result["status"] == "WAITING_USER"
    # Images generate concurrently, so which image absorbs each retry is
    # nondeterministic; assert totals instead of an exact sequence.
    assert len(sleep_calls) == 4
    assert set(sleep_calls) <= {15.0, 30.0, 60.0, 90.0}
    assert image_provider.calls == 7
    assert len(DirectionOutput.model_validate(result["direction_output"]).directions) == 3


def test_sparse_information_interrupts_and_resumes_from_checkpoint(workflow) -> None:
    config = _config("thread-sparse")
    first_result = workflow.invoke(
        {
            "project_id": "project-sparse",
            "brand_spec": BrandSpec(project_name="新品牌").model_dump(mode="json"),
            "status": "INTAKE",
        },
        config=config,
    )

    assert first_result["status"] == "NEEDS_INPUT"
    intake_output = IntakeOutput.model_validate(first_result["intake_output"])
    assert {question.field_path for question in intake_output.questions} == {
        "industry",
        "brand_background",
        "target_audiences",
        "style_keywords",
    }
    assert first_result["__interrupt__"][0].value["kind"] == "intake_questions"

    resumed = workflow.invoke(
        Command(
            resume={
                "answers": [
                    {"field_path": "industry", "value": "茶饮"},
                    {
                        "field_path": "brand_background",
                        "value": "提供当代东方风味的城市茶饮。",
                    },
                    {
                        "field_path": "target_audiences",
                        "value": ["年轻城市消费者"],
                    },
                    {
                        "field_path": "style_keywords",
                        "value": ["当代", "东方", "清爽"],
                    },
                ]
            }
        ),
        config=config,
    )

    assert resumed["status"] == "WAITING_USER"
    assert len(DirectionOutput.model_validate(resumed["direction_output"]).directions) == 3


def test_conflicting_information_is_reported_instead_of_invented(workflow) -> None:
    conflicting = _complete_spec().model_copy(
        update={
            "price_positioning": "极低价儿童市场",
            "style_keywords": ["高端奢华", "冷峻"],
        }
    )
    result = workflow.invoke(
        {
            "project_id": "project-conflict",
            "brand_spec": conflicting.model_dump(mode="json"),
            "status": "INTAKE",
        },
        config=_config("thread-conflict"),
    )

    assert result["status"] == "NEEDS_INPUT"
    intake_output = IntakeOutput.model_validate(result["intake_output"])
    assert [conflict.code for conflict in intake_output.conflicts] == ["POSITIONING_STYLE_CONFLICT"]
    assert intake_output.questions[0].field_path == "style_keywords"


def test_full_workflow_reaches_export_ready_after_ip_confirmation(workflow) -> None:
    config = _config("thread-with-ip")
    result = workflow.invoke(
        {
            "project_id": "project-with-ip",
            "brand_spec": _complete_spec().model_dump(mode="json"),
            "status": "INTAKE",
        },
        config=config,
    )
    assert result["__interrupt__"][0].value["kind"] == "direction_decision"

    result = _resume(
        workflow,
        config,
        {
            "version_id": str(_version("directions-ip")),
            "selected_item_id": "direction-warm",
        },
    )
    assert result["__interrupt__"][0].value["kind"] == "logo_decision"

    result = _resume(
        workflow,
        config,
        {
            "version_id": str(_version("logo-ip")),
            "selected_item_id": "logo-symbol",
        },
    )
    assert result["__interrupt__"][0].value["kind"] == "ip_decision"
    assert result["selected_version_ids"] == {
        "DIRECTIONS": str(_version("directions-ip")),
        "LOGO": str(_version("logo-ip")),
    }
    ip_output = IPOutput.model_validate(result["ip_output"])
    logo_output = LogoOutput.model_validate(result["logo_output"])
    selected_logo = next(item for item in logo_output.concepts if item.id == "logo-symbol")
    assert ip_output.preview_asset_id
    assert ip_output.character.brand_connection

    result = _resume(
        workflow,
        config,
        {"version_id": str(_version("ip")), "confirmed": True},
    )
    assert selected_logo.preview_asset_id
    assert result["status"] == "EXPORT_READY"
    assert result["selected_version_ids"] == {
        "DIRECTIONS": str(_version("directions-ip")),
        "LOGO": str(_version("logo-ip")),
        "IP": str(_version("ip")),
    }
    assert not result.get("__interrupt__")


def test_graph_can_resume_after_worker_rebuild() -> None:
    checkpointer = InMemorySaver()
    artifact_writer = InMemoryArtifactWriter()
    invocation_recorder = InMemoryInvocationRecorder()

    def build():
        return build_brand_workflow(
            text_provider=FakeTextModelProvider(),
            image_provider=FakeImageModelProvider(),
            artifact_writer=artifact_writer,
            invocation_recorder=invocation_recorder,
            checkpointer=checkpointer,
        )

    config = _config("thread-restart")
    first_worker = build()
    interrupted = first_worker.invoke(
        {
            "project_id": "project-restart",
            "brand_spec": _complete_spec().model_dump(mode="json"),
            "status": "INTAKE",
        },
        config=config,
    )
    assert interrupted["__interrupt__"][0].value["kind"] == "direction_decision"

    rebuilt_worker = build()
    resumed = rebuilt_worker.invoke(
        Command(
            resume={
                "version_id": str(_version("restart-directions")),
                "selected_item_id": "direction-clear",
            }
        ),
        config=config,
    )

    assert resumed["__interrupt__"][0].value["kind"] == "logo_decision"
    assert resumed["selected_direction_id"] == "direction-clear"
    assert any(record.capability.value == "LOGO" for record in invocation_recorder.records)


def test_logo_selection_resumes_after_worker_rebuild_and_reaches_ip_decision() -> None:
    checkpointer = InMemorySaver()
    artifact_writer = InMemoryArtifactWriter()
    invocation_recorder = InMemoryInvocationRecorder()

    def build():
        return build_brand_workflow(
            text_provider=FakeTextModelProvider(),
            image_provider=FakeImageModelProvider(),
            artifact_writer=artifact_writer,
            invocation_recorder=invocation_recorder,
            checkpointer=checkpointer,
        )

    config = _config("thread-logo-to-ip-restart")
    first_worker = build()
    first_worker.invoke(
        {
            "project_id": "project-logo-to-ip-restart",
            "brand_spec": _complete_spec().model_dump(mode="json"),
            "status": "INTAKE",
        },
        config=config,
    )
    waiting_for_logo = _resume(
        first_worker,
        config,
        {
            "version_id": str(_version("restart-directions-for-vi")),
            "selected_item_id": "direction-clear",
        },
    )
    logo_output = LogoOutput.model_validate(waiting_for_logo["logo_output"])
    selected_logo = next(
        concept for concept in logo_output.concepts if concept.id == "logo-wordmark"
    )
    assert waiting_for_logo["__interrupt__"][0].value["kind"] == "logo_decision"

    rebuilt_worker = build()
    waiting_for_ip = _resume(
        rebuilt_worker,
        config,
        {
            "version_id": str(_version("restart-logo")),
            "selected_item_id": selected_logo.id,
        },
    )
    ip_output = IPOutput.model_validate(waiting_for_ip["ip_output"])

    assert waiting_for_ip["__interrupt__"][0].value["kind"] == "ip_decision"
    assert waiting_for_ip["selected_logo_id"] == selected_logo.id
    assert waiting_for_ip["selected_version_ids"]["LOGO"] == str(_version("restart-logo"))
    assert ip_output.preview_asset_id
    assert [view.name for view in ip_output.views] == ["侧面", "背面"]
    view_asset_ids = {view.preview_asset_id for view in ip_output.views}
    assert ip_output.preview_asset_id not in view_asset_ids
    assert len(view_asset_ids) == 2
    ip_invocations = [
        record for record in invocation_recorder.records if record.capability.value == "IP"
    ]
    # One text call plus main + two turnaround view images.
    assert len(ip_invocations) == 4
    assert sum(record.image_count for record in ip_invocations) == 3


def test_ip_confirmation_reaches_export_ready_after_worker_rebuild() -> None:
    checkpointer = InMemorySaver()
    artifact_writer = InMemoryArtifactWriter()
    invocation_recorder = InMemoryInvocationRecorder()

    def build():
        return build_brand_workflow(
            text_provider=FakeTextModelProvider(),
            image_provider=FakeImageModelProvider(),
            artifact_writer=artifact_writer,
            invocation_recorder=invocation_recorder,
            checkpointer=checkpointer,
        )

    config = _config("thread-ip-export-restart")
    first_worker = build()
    first_worker.invoke(
        {
            "project_id": "project-ip-export-restart",
            "brand_spec": _complete_spec().model_dump(mode="json"),
            "status": "INTAKE",
        },
        config=config,
    )
    _resume(
        first_worker,
        config,
        {
            "version_id": str(_version("ip-export-directions")),
            "selected_item_id": "direction-clear",
        },
    )
    waiting_for_ip = _resume(
        first_worker,
        config,
        {
            "version_id": str(_version("ip-export-logo")),
            "selected_item_id": "logo-wordmark",
        },
    )
    assert waiting_for_ip["__interrupt__"][0].value["kind"] == "ip_decision"
    IPOutput.model_validate(waiting_for_ip["ip_output"])
    invocation_count_before_confirmation = len(invocation_recorder.records)
    artifact_count_before_confirmation = len(artifact_writer.items)

    rebuilt_worker = build()
    completed = _resume(
        rebuilt_worker,
        config,
        {
            "version_id": str(_version("ip-export-ip")),
            "confirmed": True,
        },
    )
    assert completed["status"] == "EXPORT_READY"
    assert completed["selected_version_ids"]["IP"] == str(_version("ip-export-ip"))
    assert set(completed["selected_version_ids"]) == {"DIRECTIONS", "LOGO", "IP"}
    assert not completed.get("__interrupt__")
    assert len(invocation_recorder.records) == invocation_count_before_confirmation
    assert len(artifact_writer.items) == artifact_count_before_confirmation
