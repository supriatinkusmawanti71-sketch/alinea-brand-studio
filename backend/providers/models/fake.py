from __future__ import annotations

import base64
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from backend.agents.schemas.brand_spec import BrandSpec
from backend.agents.schemas.common import PaletteColor
from backend.agents.schemas.directions import (
    DirectionBrief,
    DirectionDraft,
    DirectionDraftOutput,
    TypographyDirection,
)
from backend.agents.schemas.intake import (
    AnswerType,
    Conflict,
    IntakeOutput,
    Question,
)
from backend.agents.schemas.ip import (
    CharacterDefinition,
    IPDraft,
    PoseDefinition,
)
from backend.agents.schemas.logo import LogoDraft, LogoDraftOutput
from backend.agents.schemas.materials import MaterialDraft, MaterialDraftOutput
from backend.agents.schemas.proposal import ProposalOutput
from backend.agents.schemas.review import (
    ReviewCategory,
    ReviewIssue,
    ReviewOutput,
    Severity,
)
from backend.agents.schemas.vi import LayoutRule, LogoRules, TypographySystem, VIOutput
from backend.providers.models.base import (
    GeneratedImage,
    ImageGenerationRequest,
    ModelCapability,
    TextGenerationRequest,
    TextGenerationResult,
)

_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk/x8AAusB9Wl2nXsAAAAASUVORK5CYII="
)


class FakeTextModelProvider:
    """Deterministic provider used by local development and contract tests."""

    provider_name = "fake"
    model_name = "fake-structured-v1"

    def generate_structured(
        self,
        request: TextGenerationRequest,
    ) -> TextGenerationResult:
        if request.capability is ModelCapability.INTAKE:
            content = self._build_intake(request.payload)
        elif request.capability is ModelCapability.DIRECTIONS:
            content = self._build_directions(request.payload)
        elif request.capability is ModelCapability.LOGO:
            content = self._build_logo(request.payload)
        elif request.capability is ModelCapability.VI:
            content = self._build_vi(request.payload)
        elif request.capability is ModelCapability.IP:
            content = self._build_ip(request.payload)
        elif request.capability is ModelCapability.MATERIALS:
            content = self._build_materials(request.payload)
        elif request.capability is ModelCapability.REVIEW:
            content = self._build_review(request.payload)
        elif request.capability is ModelCapability.PROPOSAL:
            content = self._build_proposal(request.payload)
        else:  # pragma: no cover - the enum protects current callers
            raise ValueError(f"Unsupported capability: {request.capability}")

        output_text = json.dumps(content, ensure_ascii=False, sort_keys=True)
        return TextGenerationResult(
            provider=self.provider_name,
            model=self.model_name,
            content_json=content,
            input_tokens=max(1, len(json.dumps(request.payload, ensure_ascii=False)) // 4),
            output_tokens=max(1, len(output_text) // 4),
            latency_ms=0,
            provider_request_id=str(uuid5(NAMESPACE_URL, request.request_id)),
            finish_reason="stop",
        )

    def _build_intake(self, payload: dict[str, Any]) -> dict[str, Any]:
        brand_spec = BrandSpec.model_validate(payload["brand_spec"])
        conflicts = self._find_conflicts(brand_spec)
        questions = self._build_missing_questions(brand_spec)

        if conflicts:
            questions = [
                Question(
                    id="resolve-positioning-conflict",
                    field_path="style_keywords",
                    prompt="请确认应优先保留的品牌定位与视觉风格。",
                    reason="现有价格定位与风格目标互相冲突。",
                    required=True,
                    answer_type=AnswerType.TEXT_LIST,
                )
            ]

        return IntakeOutput(
            ready=not questions and not conflicts,
            questions=questions[:5],
            conflicts=conflicts,
        ).model_dump(mode="json")

    @staticmethod
    def _build_missing_questions(brand_spec: BrandSpec) -> list[Question]:
        definitions = [
            (
                "industry",
                "品牌所在的行业或品类是什么？",
                "行业会影响视觉语境和竞品区分。",
                AnswerType.TEXT,
            ),
            (
                "brand_background",
                "请简要介绍品牌背景、产品或服务。",
                "缺少背景时无法判断品牌承诺。",
                AnswerType.TEXT,
            ),
            (
                "target_audiences",
                "主要目标用户是谁？",
                "目标用户决定表达方式和视觉亲和度。",
                AnswerType.TEXT_LIST,
            ),
            (
                "style_keywords",
                "希望呈现哪些视觉风格关键词？",
                "风格关键词用于形成差异化方向。",
                AnswerType.TEXT_LIST,
            ),
        ]
        questions: list[Question] = []
        for field_path, prompt, reason, answer_type in definitions:
            value = getattr(brand_spec, field_path)
            if value is None or value == [] or value == "":
                questions.append(
                    Question(
                        id=f"missing-{field_path}",
                        field_path=field_path,
                        prompt=prompt,
                        reason=reason,
                        required=True,
                        answer_type=answer_type,
                    )
                )
        return questions

    @staticmethod
    def _find_conflicts(brand_spec: BrandSpec) -> list[Conflict]:
        conflicts: list[Conflict] = []
        positioning = (brand_spec.price_positioning or "").lower()
        style_text = " ".join(brand_spec.style_keywords).lower()
        if ("极低价" in positioning or "低价儿童" in positioning) and (
            "高端奢华" in style_text or "奢华" in style_text
        ):
            conflicts.append(
                Conflict(
                    code="POSITIONING_STYLE_CONFLICT",
                    field_paths=["price_positioning", "style_keywords"],
                    message="低价儿童市场定位与高端奢华风格目标存在冲突。",
                )
            )

        overlap = set(brand_spec.required_elements) & set(brand_spec.prohibited_elements)
        if overlap:
            conflicts.append(
                Conflict(
                    code="REQUIRED_PROHIBITED_CONFLICT",
                    field_paths=["required_elements", "prohibited_elements"],
                    message=f"以下元素同时被要求和禁止：{', '.join(sorted(overlap))}",
                )
            )
        return conflicts

    @staticmethod
    def _build_directions(payload: dict[str, Any]) -> dict[str, Any]:
        brand_spec = BrandSpec.model_validate(payload["brand_spec"])
        audience = "、".join(brand_spec.target_audiences)
        industry = brand_spec.industry or "品牌"
        shared = {
            "typography": TypographyDirection(
                heading_style="清晰、有识别度的现代中文标题字",
                body_style="高可读性的中性无衬线正文字体",
            ),
            "risks": ["需要在真实应用尺寸中复核可读性"],
        }
        directions = [
            DirectionDraft(
                id="direction-clear",
                name="清晰秩序",
                concept="以克制网格和高留白建立可信、稳定的品牌印象。",
                keywords=["克制", "秩序", "可信"],
                palette=[
                    PaletteColor(name="墨黑", hex="#111111", usage="主文字与标识"),
                    PaletteColor(name="暖白", hex="#F7F3EA", usage="主背景"),
                    PaletteColor(name="雾灰", hex="#B8BDC6", usage="辅助信息"),
                ],
                composition="使用稳定网格、明确层级和大面积留白。",
                rationale=f"适合向{audience}传达{industry}品牌的专业度。",
                image_prompt=f"{brand_spec.project_name} 品牌方向图，现代网格，高留白，克制可信",
                **shared,
            ),
            DirectionDraft(
                id="direction-warm",
                name="温暖连接",
                concept="用柔和色彩和圆润形态强化亲近感与情绪连接。",
                keywords=["温暖", "亲和", "自然"],
                palette=[
                    PaletteColor(name="陶土", hex="#C96F4A", usage="情绪强调"),
                    PaletteColor(name="米白", hex="#FFF7EA", usage="主背景"),
                    PaletteColor(name="苔绿", hex="#65745B", usage="自然辅助"),
                ],
                composition="使用圆润轮廓、自然材质和贴近生活的局部构图。",
                rationale=f"有助于{brand_spec.project_name}降低理解门槛并建立亲和力。",
                image_prompt=f"{brand_spec.project_name} 品牌方向图，温暖自然，圆润形态，生活感",
                **shared,
            ),
            DirectionDraft(
                id="direction-bold",
                name="鲜明先锋",
                concept="通过高对比色块和大胆比例制造快速识别与传播记忆。",
                keywords=["鲜明", "先锋", "有力"],
                palette=[
                    PaletteColor(name="电蓝", hex="#2457FF", usage="品牌主色"),
                    PaletteColor(name="亮黄", hex="#FFD84A", usage="高亮强调"),
                    PaletteColor(name="深蓝", hex="#102047", usage="稳定背景"),
                ],
                composition="使用高对比色块、非对称网格和超大标题。",
                rationale=f"适合{brand_spec.project_name}在拥挤的{industry}市场快速建立识别。",
                image_prompt=f"{brand_spec.project_name} 品牌方向图，高对比，先锋排版，大胆色块",
                **shared,
            ),
        ]
        return DirectionDraftOutput(
            brief=DirectionBrief(
                positioning=f"面向{audience}的{industry}品牌概念方案",
                audience_insight=f"目标用户关注清晰价值、可信表达和可辨识体验：{audience}",
                brand_promise=f"让{brand_spec.project_name}以一致的视觉语言表达核心价值。",
                tone="清晰、可信，并保留足够的品牌个性。",
            ),
            directions=directions,
        ).model_dump(mode="json")

    @staticmethod
    def _build_logo(payload: dict[str, Any]) -> dict[str, Any]:
        brand_spec = BrandSpec.model_validate(payload["brand_spec"])
        selected_direction = payload["selected_direction"]
        concepts = [
            LogoDraft(
                id="logo-wordmark",
                name="结构字标",
                rationale="以清晰字形建立稳定识别，适合网页与提案场景。",
                symbolism="通过字形比例表达品牌的可靠与当代感。",
                shape_language="克制几何、开放留白、横向稳定结构。",
                color_strategy="优先使用已选方向主色，并保留单色版本。",
                image_prompt=(
                    f"{brand_spec.project_name} 概念 Logo，结构字标，"
                    f"方向：{selected_direction['name']}，纯色背景，无 mockup"
                ),
            ),
            LogoDraft(
                id="logo-symbol",
                name="抽象符号",
                rationale="通过独立符号提升头像、图标和小尺寸场景的辨识度。",
                symbolism="将品牌核心关系转译为可记忆的抽象连接形态。",
                shape_language="简洁轮廓、单一视觉重心、可缩放结构。",
                color_strategy="主色与深色形成高对比，避免复杂渐变。",
                image_prompt=(
                    f"{brand_spec.project_name} 概念 Logo，抽象几何符号，"
                    f"方向：{selected_direction['name']}，纯色背景，无 mockup"
                ),
            ),
            LogoDraft(
                id="logo-combination",
                name="组合标识",
                rationale="组合文字与符号，兼顾完整表达和拆分使用。",
                symbolism="文字负责品牌名称，符号承载方向概念。",
                shape_language="符号与字标比例明确，横版与竖版均可延展。",
                color_strategy="采用方向色板中的主色与中性色组合。",
                image_prompt=(
                    f"{brand_spec.project_name} 概念 Logo，符号与字标组合，"
                    f"方向：{selected_direction['name']}，纯色背景，无 mockup"
                ),
            ),
            LogoDraft(
                id="logo-emblem",
                name="徽章图标",
                rationale="用更完整的封装形态提升品牌在包装、头像和活动物料中的存在感。",
                symbolism="将方向关键词整合为一个可独立使用的品牌识别容器。",
                shape_language="圆角边界、中心符号、简洁层次，避免复杂装饰。",
                color_strategy="以方向主色建立识别，辅以浅底和深色描边保证清晰度。",
                image_prompt=(
                    f"{brand_spec.project_name} 概念 Logo，现代徽章图标，"
                    f"方向：{selected_direction['name']}，白底居中，扁平矢量，无 mockup"
                ),
            ),
        ]
        return LogoDraftOutput(concepts=concepts).model_dump(mode="json")

    @staticmethod
    def _build_vi(payload: dict[str, Any]) -> dict[str, Any]:
        selected_logo = payload["selected_logo"]
        return VIOutput(
            palette=[
                PaletteColor(name="品牌主色", hex="#2457FF", usage="标识与核心按钮"),
                PaletteColor(name="深色", hex="#111827", usage="正文与深色背景"),
                PaletteColor(name="浅色", hex="#F8FAFC", usage="页面与提案背景"),
            ],
            typography=TypographySystem(
                heading_style="现代中文无衬线粗体，强调清晰层级",
                body_style="中性无衬线常规字重，保证长文可读性",
                fallbacks=["PingFang SC", "Microsoft YaHei", "sans-serif"],
                usage_rules=["标题最多使用两种字重", "正文避免全大写或过密字距"],
            ),
            logo_rules=LogoRules(
                clear_space="四周至少保留标识高度 1/4 的安全空间",
                minimum_size="数字界面宽度不小于 24px，印刷宽度不小于 8mm",
                background_rules=["优先使用纯色高对比背景", "复杂图片上增加纯色承载区"],
                prohibited_uses=["禁止拉伸", "禁止任意描边", "禁止替换非规范色"],
            ),
            layouts=[
                LayoutRule(
                    name="网页内容布局",
                    grid="12 栏网格，主要内容占 8–10 栏",
                    spacing="以 8px 为基础间距单位",
                    example_usage="品牌首页、项目介绍和提案内容页",
                )
            ],
            source_logo_asset_id=selected_logo["preview_asset_id"],
        ).model_dump(mode="json")

    @staticmethod
    def _build_ip(payload: dict[str, Any]) -> dict[str, Any]:
        brand_spec = BrandSpec.model_validate(payload["brand_spec"])
        return IPDraft(
            character=CharacterDefinition(
                name=f"{brand_spec.project_name}伙伴",
                role="作为品牌内容与服务场景中的友好引导者。",
                personality=["可靠", "好奇", "亲和"],
                appearance="由品牌主色、简洁圆润轮廓和清晰面部表情构成。",
                brand_connection="延续已确认 Logo 的几何语言与 VI 色彩规范。",
            ),
            pose=PoseDefinition(
                name="正面欢迎姿态",
                description="正面站立并以开放手势欢迎用户，背景简洁。",
            ),
            image_prompt=f"{brand_spec.project_name} 品牌 IP，正面欢迎姿态，简洁角色设定图",
        ).model_dump(mode="json")

    @staticmethod
    def _build_materials(payload: dict[str, Any]) -> dict[str, Any]:
        brand_spec = BrandSpec.model_validate(payload["brand_spec"])
        used_asset_ids = payload["used_asset_ids"]
        scenes = [
            MaterialDraft(
                id="material-digital-cover",
                scenario_id="DIGITAL_COVER",
                name="社交媒体封面",
                rationale="验证品牌在横向数字传播场景中的识别和信息层级。",
                used_asset_ids=used_asset_ids,
                image_prompt=f"{brand_spec.project_name} 社交媒体封面品牌应用图，真实排版 mockup",
            ),
            MaterialDraft(
                id="material-packaging",
                scenario_id="PACKAGING",
                name="基础包装",
                rationale="验证 Logo 与 VI 在实体承载物上的比例和色彩效果。",
                used_asset_ids=used_asset_ids,
                image_prompt=f"{brand_spec.project_name} 基础包装品牌应用图，简洁棚拍 mockup",
            ),
        ]
        return MaterialDraftOutput(scenes=scenes).model_dump(mode="json")

    @staticmethod
    def _build_review(payload: dict[str, Any]) -> dict[str, Any]:
        forced_category = payload.get("force_issue_category")
        issues: list[ReviewIssue] = []
        if forced_category:
            category = ReviewCategory(forced_category)
            issues.append(
                ReviewIssue(
                    id="review-forced-issue",
                    severity=Severity.BLOCKER,
                    category=category,
                    evidence="固定评测夹具触发了一个可复现问题。",
                    suggestion="返回对应阶段修复后重新审稿。",
                    target_stage="MATERIALS",
                    target_asset_ids=payload.get("material_asset_ids", []),
                )
            )
        return ReviewOutput(
            passed=not issues,
            summary="所有已确认阶段的结构、约束和资产引用已完成检查。",
            issues=issues,
        ).model_dump(mode="json", by_alias=True)

    @staticmethod
    def _build_proposal(payload: dict[str, Any]) -> dict[str, Any]:
        proposal = ProposalOutput.model_validate(payload["proposal_contract"])
        return proposal.model_dump(mode="json")


class FakeImageModelProvider:
    """Returns deterministic valid PNG bytes without external calls."""

    provider_name = "fake"
    model_name = "fake-image-v1"

    def generate(self, request: ImageGenerationRequest) -> list[GeneratedImage]:
        return [
            GeneratedImage(
                provider=self.provider_name,
                model=self.model_name,
                content=_ONE_PIXEL_PNG,
                mime_type="image/png",
                width=1,
                height=1,
                provider_request_id=str(uuid5(NAMESPACE_URL, f"{request.request_id}:{index}")),
                latency_ms=0,
            )
            for index in range(request.count)
        ]
