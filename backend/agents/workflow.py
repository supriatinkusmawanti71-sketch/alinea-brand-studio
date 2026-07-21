from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from backend.agents.errors import InvalidModelOutputError
from backend.agents.ports import (
    ArtifactWriter,
    InvocationRecorder,
    InvocationStatus,
    ModelInvocationRecord,
)
from backend.agents.prompts import build_model_messages
from backend.agents.registry import AgentKey, get_agent_contract
from backend.agents.schemas.brand_spec import BrandSpec
from backend.agents.schemas.directions import (
    Direction,
    DirectionDraftOutput,
    DirectionOutput,
)
from backend.agents.schemas.intake import IntakeOutput, IntakeResumePayload
from backend.agents.schemas.ip import IPDraft, IPOutput, IPView
from backend.agents.schemas.logo import LogoConcept, LogoDraft, LogoDraftOutput, LogoOutput
from backend.agents.schemas.workflow_controls import (
    ConfirmStageDecision,
    SelectItemDecision,
)
from backend.providers.models.base import (
    GeneratedImage,
    ImageGenerationRequest,
    ImageModelProvider,
    ModelCapability,
    TextGenerationRequest,
    TextModelProvider,
)

_LOGO_IMAGE_PROMPT_MAX_CHARS = 220
_IMAGE_GENERATION_RETRY_DELAYS_SECONDS = (15, 30, 60, 90)
_IMAGE_GENERATION_MAX_ATTEMPTS = len(_IMAGE_GENERATION_RETRY_DELAYS_SECONDS) + 1
# Image models take 60-150s per image; leave headroom above the observed max.
_IMAGE_REQUEST_TIMEOUT_SECONDS = 300
# Independent images within one stage generate concurrently. Provider HTTP
# clients are thread-safe; recorder/writer calls stay on the caller thread.
_IMAGE_PARALLELISM = 4


@dataclass
class _ImageOutcome:
    """Result of one provider image call, produced on a worker thread.

    Carries the invocation audit records instead of writing them directly:
    the recorder and artifact writer share a DB session that is not
    thread-safe, so the caller thread flushes records and stores the image.
    """

    request_id: str
    records: list[ModelInvocationRecord] = field(default_factory=list)
    image: GeneratedImage | None = None
    error: Exception | None = None
_IP_VIEW_SPECS = (
    ("view-side", "侧面", "正侧面视角，完整展示角色轮廓与侧面细节"),
    ("view-back", "背面", "正背面视角，完整展示角色背部造型"),
)


def build_ip_view_prompt(draft: IPDraft, view_name: str, view_instruction: str) -> str:
    """Build a turnaround-view prompt anchored to the main image reference."""

    appearance = draft.character.appearance.strip()[:300]
    return (
        f"参考图中角色的{view_name}视图：{view_instruction}。"
        f"必须与参考图中的角色保持完全一致的造型、配色、材质、比例与风格，"
        f"白底居中，完整角色，干净轮廓，便于抠图，不出现复杂背景。"
        f"角色外观设定：{appearance}"
    )


def _first_unique(values: Sequence[str], *, limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in result:
            continue
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def _logo_mark_type(draft: LogoDraft) -> str:
    text = f"{draft.id} {draft.name}".lower()
    if "wordmark" in text or "字标" in text:
        return "结构字标"
    if "combination" in text or "组合" in text:
        return "符号与字标组合"
    if "emblem" in text or "徽章" in text:
        return "现代徽章图标"
    if "symbol" in text or "符号" in text:
        return "抽象几何符号"
    return "简洁抽象标识"


def build_short_logo_image_prompt(
    brand_spec: BrandSpec,
    selected_direction: Direction,
    draft: LogoDraft,
) -> str:
    """Build a compact image prompt for stricter image providers."""

    brand_name = brand_spec.project_name.strip() or "品牌"
    style_words = _first_unique(
        [*selected_direction.keywords, *brand_spec.style_keywords],
        limit=3,
    )
    style = "、".join(style_words) if style_words else "现代克制"
    palette_names = _first_unique([color.name for color in selected_direction.palette], limit=2)
    palette = f"主色{'、'.join(palette_names)}" if palette_names else "主色克制清爽"
    prompt = (
        f"{brand_name} {draft.name} Logo，{_logo_mark_type(draft)}，{style}风格，"
        f"{palette}，白底居中，扁平矢量，简洁品牌名占位，高识别度"
    )
    return prompt[:_LOGO_IMAGE_PROMPT_MAX_CHARS]


class BrandWorkflowState(TypedDict, total=False):
    project_id: str
    brand_spec: dict[str, Any]
    status: str
    intake_output: dict[str, Any]
    direction_output: dict[str, Any]
    selected_direction_id: str
    logo_output: dict[str, Any]
    selected_logo_id: str
    ip_output: dict[str, Any]
    selected_version_ids: dict[str, str]
    # User feedback attached to a regeneration run; consumed by the next
    # generation node and then cleared.
    regenerate_feedback: str


def build_brand_workflow(
    *,
    text_provider: TextModelProvider,
    image_provider: ImageModelProvider,
    artifact_writer: ArtifactWriter,
    invocation_recorder: InvocationRecorder,
    checkpointer: Any,
    interrupt_before: Sequence[str] = (),
) -> Any:
    """Build the deterministic Brand Agent graph around human interrupts.

    Business persistence is deliberately absent. The application layer owns
    stage versions, decisions, outbox delivery, and the production checkpointer.
    """

    def generate_text(
        state: BrandWorkflowState,
        *,
        capability: ModelCapability,
        payload: dict[str, Any],
        output_model: Any,
        prompt_version: str,
    ) -> Any:
        request = TextGenerationRequest(
            request_id=f"{state['project_id']}:{capability.value.lower()}",
            capability=capability,
            prompt_version=prompt_version,
            messages=build_model_messages(capability, payload),
            json_schema=output_model.model_json_schema(),
        )
        try:
            result = text_provider.generate_structured(request)
        except Exception as error:
            invocation_recorder.record_model_invocation(
                ModelInvocationRecord(
                    request_id=request.request_id,
                    capability=capability,
                    prompt_version=request.prompt_version,
                    provider=getattr(text_provider, "provider_name", "unknown"),
                    model=getattr(text_provider, "model_name", "unknown"),
                    status=InvocationStatus.FAILED,
                    error_code=getattr(error, "code", "PROVIDER_UNEXPECTED"),
                )
            )
            raise
        try:
            validated = output_model.model_validate(result.content_json)
            invocation_recorder.record_model_invocation(
                ModelInvocationRecord(
                    request_id=request.request_id,
                    capability=capability,
                    prompt_version=request.prompt_version,
                    provider=result.provider,
                    model=result.model,
                    status=InvocationStatus.SUCCEEDED,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    latency_ms=result.latency_ms,
                )
            )
            return validated
        except ValidationError as first_error:
            invocation_recorder.record_model_invocation(
                ModelInvocationRecord(
                    request_id=request.request_id,
                    capability=capability,
                    prompt_version=request.prompt_version,
                    provider=result.provider,
                    model=result.model,
                    status=InvocationStatus.INVALID_OUTPUT,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    latency_ms=result.latency_ms,
                    error_code="INVALID_MODEL_OUTPUT",
                )
            )
            repair_request = TextGenerationRequest(
                request_id=f"{request.request_id}:repair",
                capability=capability,
                prompt_version=f"{prompt_version}-repair",
                messages=build_model_messages(
                    capability,
                    payload,
                    repair_errors=first_error.errors(
                        include_url=False,
                        include_context=False,
                        include_input=False,
                    ),
                    invalid_output=result.content_json,
                ),
                json_schema=output_model.model_json_schema(),
            )
            try:
                repaired = text_provider.generate_structured(repair_request)
            except Exception as error:
                invocation_recorder.record_model_invocation(
                    ModelInvocationRecord(
                        request_id=repair_request.request_id,
                        capability=capability,
                        prompt_version=repair_request.prompt_version,
                        provider=getattr(text_provider, "provider_name", "unknown"),
                        model=getattr(text_provider, "model_name", "unknown"),
                        status=InvocationStatus.FAILED,
                        error_code=getattr(error, "code", "PROVIDER_UNEXPECTED"),
                    )
                )
                raise
            try:
                validated = output_model.model_validate(repaired.content_json)
                invocation_recorder.record_model_invocation(
                    ModelInvocationRecord(
                        request_id=repair_request.request_id,
                        capability=capability,
                        prompt_version=repair_request.prompt_version,
                        provider=repaired.provider,
                        model=repaired.model,
                        status=InvocationStatus.SUCCEEDED,
                        input_tokens=repaired.input_tokens,
                        output_tokens=repaired.output_tokens,
                        latency_ms=repaired.latency_ms,
                    )
                )
                return validated
            except ValidationError as second_error:
                invocation_recorder.record_model_invocation(
                    ModelInvocationRecord(
                        request_id=repair_request.request_id,
                        capability=capability,
                        prompt_version=repair_request.prompt_version,
                        provider=repaired.provider,
                        model=repaired.model,
                        status=InvocationStatus.INVALID_OUTPUT,
                        input_tokens=repaired.input_tokens,
                        output_tokens=repaired.output_tokens,
                        latency_ms=repaired.latency_ms,
                        error_code="INVALID_MODEL_OUTPUT",
                    )
                )
                raise InvalidModelOutputError(
                    f"{capability.value} output remained invalid after one repair"
                ) from second_error

    def invoke_image_provider(
        *,
        project_id: str,
        item_kind: str,
        item_id: str,
        prompt: str,
        reference_asset_ids: list[str] | None = None,
    ) -> _ImageOutcome:
        """Call the image provider with retries. Thread-safe: touches neither
        the invocation recorder nor the artifact writer."""

        image_request_id = f"{project_id}:{item_kind}:{item_id}"
        image_capability = {
            "direction": ModelCapability.DIRECTIONS,
            "logo": ModelCapability.LOGO,
            "ip": ModelCapability.IP,
        }[item_kind]
        request = ImageGenerationRequest(
            request_id=image_request_id,
            capability=image_capability,
            prompt=prompt,
            reference_artifact_ids=reference_asset_ids or [],
            count=1,
            timeout_seconds=_IMAGE_REQUEST_TIMEOUT_SECONDS,
        )
        outcome = _ImageOutcome(request_id=image_request_id)

        def failure_record(error: Exception | None, image_count: int | None = None):
            extra: dict[str, Any] = {"image_count": image_count} if image_count is not None else {}
            return ModelInvocationRecord(
                request_id=request.request_id,
                capability=image_capability,
                prompt_version=f"{item_kind}-image-v1",
                provider=getattr(image_provider, "provider_name", "unknown"),
                model=getattr(image_provider, "model_name", "unknown"),
                status=InvocationStatus.FAILED,
                error_code=(
                    "INVALID_IMAGE_COUNT"
                    if image_count is not None
                    else getattr(error, "code", "PROVIDER_UNEXPECTED")
                ),
                **extra,
            )

        images = None
        for attempt_index in range(_IMAGE_GENERATION_MAX_ATTEMPTS):
            try:
                images = image_provider.generate(request)
                break
            except Exception as error:
                outcome.records.append(failure_record(error))
                is_last_attempt = attempt_index + 1 >= _IMAGE_GENERATION_MAX_ATTEMPTS
                if not getattr(error, "retryable", False) or is_last_attempt:
                    outcome.error = error
                    return outcome
                retry_after = getattr(error, "retry_after_seconds", None)
                fallback_delay = _IMAGE_GENERATION_RETRY_DELAYS_SECONDS[attempt_index]
                time.sleep(float(retry_after or fallback_delay))
        if images is None:
            outcome.error = ValueError(f"{item_kind} image generation did not return a response")
            return outcome
        if len(images) != 1:
            outcome.records.append(failure_record(None, image_count=len(images)))
            outcome.error = ValueError(f"{item_kind} item must produce exactly one image")
            return outcome
        outcome.records.append(
            ModelInvocationRecord(
                request_id=request.request_id,
                capability=image_capability,
                prompt_version=f"{item_kind}-image-v1",
                provider=images[0].provider,
                model=images[0].model,
                status=InvocationStatus.SUCCEEDED,
                image_count=1,
                latency_ms=images[0].latency_ms,
            )
        )
        outcome.image = images[0]
        return outcome

    def flush_outcome_records(outcomes: Sequence[_ImageOutcome]) -> None:
        for outcome in outcomes:
            for record in outcome.records:
                invocation_recorder.record_model_invocation(record)

    def first_outcome_error(outcomes: Sequence[_ImageOutcome]) -> Exception | None:
        for outcome in outcomes:
            if outcome.error is not None:
                return outcome.error
        return None

    def run_image_calls_concurrently(
        calls: Sequence[Callable[[], _ImageOutcome]],
    ) -> list[_ImageOutcome]:
        if len(calls) <= 1:
            return [call() for call in calls]
        with ThreadPoolExecutor(max_workers=min(_IMAGE_PARALLELISM, len(calls))) as pool:
            return list(pool.map(lambda call: call(), calls))

    def generate_one_image(
        state: BrandWorkflowState,
        *,
        item_kind: str,
        item_id: str,
        prompt: str,
        reference_asset_ids: list[str] | None = None,
    ) -> UUID:
        outcome = invoke_image_provider(
            project_id=state["project_id"],
            item_kind=item_kind,
            item_id=item_id,
            prompt=prompt,
            reference_asset_ids=reference_asset_ids,
        )
        flush_outcome_records([outcome])
        if outcome.error is not None:
            raise outcome.error
        stored = artifact_writer.store_generated_image(
            request_id=outcome.request_id,
            image=outcome.image,
        )
        return stored.artifact_id

    def generate_image_batch(
        state: BrandWorkflowState,
        *,
        item_kind: str,
        items: Sequence[Any],
        prompt_for: Callable[[Any], str],
        references_for: Callable[[Any], list[str]] | None = None,
    ) -> list[UUID]:
        outcomes = run_image_calls_concurrently(
            [
                (
                    lambda item=item: invoke_image_provider(
                        project_id=state["project_id"],
                        item_kind=item_kind,
                        item_id=item.id,
                        prompt=prompt_for(item),
                        reference_asset_ids=(
                            references_for(item) if references_for else None
                        ),
                    )
                )
                for item in items
            ]
        )
        flush_outcome_records(outcomes)
        error = first_outcome_error(outcomes)
        if error is not None:
            raise error
        artifact_ids: list[UUID] = []
        try:
            for outcome in outcomes:
                stored = artifact_writer.store_generated_image(
                    request_id=outcome.request_id,
                    image=outcome.image,
                )
                artifact_ids.append(stored.artifact_id)
        except Exception:
            artifact_writer.discard_temporary_artifacts(artifact_ids)
            raise
        return artifact_ids

    def with_version(
        state: BrandWorkflowState,
        stage: str,
        version_id: UUID,
    ) -> dict[str, str]:
        versions = dict(state.get("selected_version_ids", {}))
        versions[stage] = str(version_id)
        return versions

    def analyze_intake(state: BrandWorkflowState) -> BrandWorkflowState:
        brand_spec = BrandSpec.model_validate(state["brand_spec"])
        intake_output = generate_text(
            state,
            capability=ModelCapability.INTAKE,
            payload={"brand_spec": brand_spec.model_dump(mode="json")},
            output_model=IntakeOutput,
            prompt_version="intake-v1",
        )
        return {
            "intake_output": intake_output.model_dump(mode="json"),
            "status": "DIRECTIONS" if intake_output.ready else "NEEDS_INPUT",
        }

    def route_after_intake(
        state: BrandWorkflowState,
    ) -> Literal["await_intake_answers", "generate_directions"]:
        intake_output = IntakeOutput.model_validate(state["intake_output"])
        return "generate_directions" if intake_output.ready else "await_intake_answers"

    def await_intake_answers(state: BrandWorkflowState) -> BrandWorkflowState:
        intake_output = IntakeOutput.model_validate(state["intake_output"])
        resume_value = interrupt(
            {
                "kind": "intake_questions",
                "questions": [
                    question.model_dump(mode="json") for question in intake_output.questions
                ],
                "conflicts": [
                    conflict.model_dump(mode="json") for conflict in intake_output.conflicts
                ],
            }
        )
        resume_payload = IntakeResumePayload.model_validate(resume_value)
        brand_spec = BrandSpec.model_validate(state["brand_spec"])
        updated_spec = brand_spec.apply_user_answers(
            [(answer.field_path, answer.value) for answer in resume_payload.answers],
            source_id=f"{state['project_id']}:intake-resume",
        )
        return {
            "brand_spec": updated_spec.model_dump(mode="json"),
            "status": "INTAKE",
        }

    def generate_directions(state: BrandWorkflowState) -> BrandWorkflowState:
        agent = get_agent_contract(AgentKey.ART_DIRECTOR)
        brand_spec = BrandSpec.model_validate(state["brand_spec"])
        draft_output = generate_text(
            state,
            capability=agent.capability,
            payload={"brand_spec": brand_spec.model_dump(mode="json")},
            output_model=DirectionDraftOutput,
            prompt_version=agent.prompt_version,
        )
        asset_ids = generate_image_batch(
            state,
            item_kind="direction",
            items=draft_output.directions,
            prompt_for=lambda draft: draft.image_prompt,
        )
        directions = [
            Direction(
                **draft.model_dump(),
                preview_asset_id=asset_id,
            )
            for draft, asset_id in zip(draft_output.directions, asset_ids, strict=True)
        ]
        output = DirectionOutput(brief=draft_output.brief, directions=directions)
        return {
            "direction_output": output.model_dump(mode="json"),
            "status": "WAITING_USER",
        }

    def await_direction_decision(state: BrandWorkflowState) -> BrandWorkflowState:
        output = DirectionOutput.model_validate(state["direction_output"])
        decision = SelectItemDecision.model_validate(
            interrupt(
                {
                    "kind": "direction_decision",
                    "direction_output": output.model_dump(mode="json"),
                }
            )
        )
        if decision.selected_item_id not in {item.id for item in output.directions}:
            raise ValueError("Selected direction does not exist in current output")
        return {
            "selected_direction_id": decision.selected_item_id,
            "selected_version_ids": with_version(state, "DIRECTIONS", decision.version_id),
            "status": "LOGO",
        }

    def generate_logo(state: BrandWorkflowState) -> BrandWorkflowState:
        agent = get_agent_contract(AgentKey.LOGO_DESIGNER)
        brand_spec = BrandSpec.model_validate(state["brand_spec"])
        directions = DirectionOutput.model_validate(state["direction_output"])
        selected = next(
            item for item in directions.directions if item.id == state["selected_direction_id"]
        )
        payload: dict[str, Any] = {
            "brand_spec": brand_spec.model_dump(mode="json"),
            "selected_direction": selected.model_dump(mode="json"),
        }
        feedback = state.get("regenerate_feedback")
        if feedback:
            payload["user_feedback"] = feedback
        drafts = generate_text(
            state,
            capability=agent.capability,
            payload=payload,
            output_model=LogoDraftOutput,
            prompt_version=agent.prompt_version,
        )
        asset_ids = generate_image_batch(
            state,
            item_kind="logo",
            items=drafts.concepts,
            prompt_for=lambda draft: build_short_logo_image_prompt(brand_spec, selected, draft),
            references_for=lambda _: [str(selected.preview_asset_id)],
        )
        concepts = [
            LogoConcept(
                **draft.model_dump(),
                preview_asset_id=asset_id,
            )
            for draft, asset_id in zip(drafts.concepts, asset_ids, strict=True)
        ]
        return {
            "logo_output": LogoOutput(concepts=concepts).model_dump(mode="json"),
            "status": "WAITING_USER",
            "regenerate_feedback": "",
        }

    def await_logo_decision(state: BrandWorkflowState) -> BrandWorkflowState:
        output = LogoOutput.model_validate(state["logo_output"])
        decision = SelectItemDecision.model_validate(
            interrupt(
                {
                    "kind": "logo_decision",
                    "logo_output": output.model_dump(mode="json"),
                }
            )
        )
        if decision.selected_item_id not in {item.id for item in output.concepts}:
            raise ValueError("Selected logo does not exist in current output")
        return {
            "selected_logo_id": decision.selected_item_id,
            "selected_version_ids": with_version(state, "LOGO", decision.version_id),
            "status": "IP",
        }

    def generate_ip(state: BrandWorkflowState) -> BrandWorkflowState:
        agent = get_agent_contract(AgentKey.IP_DESIGNER)
        brand_spec = BrandSpec.model_validate(state["brand_spec"])
        logo_output = LogoOutput.model_validate(state["logo_output"])
        selected_logo = next(
            item for item in logo_output.concepts if item.id == state["selected_logo_id"]
        )
        payload: dict[str, Any] = {
            "brand_spec": brand_spec.model_dump(mode="json"),
            "selected_logo": selected_logo.model_dump(mode="json"),
        }
        feedback = state.get("regenerate_feedback")
        if feedback:
            payload["user_feedback"] = feedback
        draft = generate_text(
            state,
            capability=agent.capability,
            payload=payload,
            output_model=IPDraft,
            prompt_version=agent.prompt_version,
        )
        main_asset_id = generate_one_image(
            state,
            item_kind="ip",
            item_id="primary",
            prompt=draft.image_prompt,
            reference_asset_ids=[str(selected_logo.preview_asset_id)],
        )
        generated_asset_ids = [main_asset_id]
        views: list[IPView] = []
        try:
            # Both turnaround views reference the stored main image, so they
            # are independent of each other and generate concurrently.
            view_outcomes = run_image_calls_concurrently(
                [
                    (
                        lambda spec=spec: invoke_image_provider(
                            project_id=state["project_id"],
                            item_kind="ip",
                            item_id=spec[0],
                            prompt=build_ip_view_prompt(draft, spec[1], spec[2]),
                            reference_asset_ids=[str(main_asset_id)],
                        )
                    )
                    for spec in _IP_VIEW_SPECS
                ]
            )
            flush_outcome_records(view_outcomes)
            error = first_outcome_error(view_outcomes)
            if error is not None:
                raise error
            for (_, view_name, _instruction), outcome in zip(
                _IP_VIEW_SPECS, view_outcomes, strict=True
            ):
                stored = artifact_writer.store_generated_image(
                    request_id=outcome.request_id,
                    image=outcome.image,
                )
                generated_asset_ids.append(stored.artifact_id)
                views.append(IPView(name=view_name, preview_asset_id=stored.artifact_id))
        except Exception:
            artifact_writer.discard_temporary_artifacts(generated_asset_ids)
            raise
        output = IPOutput(
            **draft.model_dump(),
            preview_asset_id=main_asset_id,
            views=views,
        )
        return {
            "ip_output": output.model_dump(mode="json"),
            "status": "WAITING_USER",
            "regenerate_feedback": "",
        }

    def await_ip_decision(state: BrandWorkflowState) -> BrandWorkflowState:
        output = IPOutput.model_validate(state["ip_output"])
        decision = ConfirmStageDecision.model_validate(
            interrupt(
                {
                    "kind": "ip_decision",
                    "ip_output": output.model_dump(mode="json"),
                }
            )
        )
        return {
            "selected_version_ids": with_version(state, "IP", decision.version_id),
            "status": "EXPORT_READY",
        }

    builder = StateGraph(BrandWorkflowState)
    builder.add_node("analyze_intake", analyze_intake)
    builder.add_node("await_intake_answers", await_intake_answers)
    builder.add_node("generate_directions", generate_directions)
    builder.add_node("await_direction_decision", await_direction_decision)
    builder.add_node("generate_logo", generate_logo)
    builder.add_node("await_logo_decision", await_logo_decision)
    builder.add_node("generate_ip", generate_ip)
    builder.add_node("await_ip_decision", await_ip_decision)

    builder.add_edge(START, "analyze_intake")
    builder.add_conditional_edges("analyze_intake", route_after_intake)
    # Intake asks at most one round of questions: once the user has answered,
    # proceed straight to directions instead of re-analyzing (which could ask
    # again and stall the flow).
    builder.add_edge("await_intake_answers", "generate_directions")
    builder.add_edge("generate_directions", "await_direction_decision")
    builder.add_edge("await_direction_decision", "generate_logo")
    builder.add_edge("generate_logo", "await_logo_decision")
    builder.add_edge("await_logo_decision", "generate_ip")
    builder.add_edge("generate_ip", "await_ip_decision")
    builder.add_edge("await_ip_decision", END)
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=list(interrupt_before),
    )
