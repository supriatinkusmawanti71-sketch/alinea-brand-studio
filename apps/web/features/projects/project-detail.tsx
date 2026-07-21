import { Button, EmptyState, ErrorState, LoadingState } from "@/components/ui";
import { StageNavigation } from "@/components/workbench/stage-navigation";
import { DirectionsResult } from "@/features/directions";
import type { DirectionOutput } from "@/features/directions";
import { IntakeQuestions } from "@/features/intake/intake-questions";
import { LogoResult } from "@/features/logo";
import type { LogoOutput } from "@/features/logo";
import type {
  VersionItemSelection,
  WorkbenchStage,
  WorkbenchStageSummary,
  WorkbenchStageStatus,
} from "@/features/workbench/types";
import { apiClient } from "@/lib/api/client";
import type {
  DecisionStateResponse,
  IntakeAnswer,
  IntakeResult,
  JsonValue,
  ProjectDetailResponse,
  ProjectStateResponse,
  StageDecisionRequest,
  StageRunDetailResponse,
  StageRunResponse,
  StageVersionStateResponse,
} from "@/lib/api/types";

import { BRAND_SPEC_FIELDS } from "./fields";

type ProjectDetailProps = {
  activeRun: StageRunDetailResponse | null;
  isLoading: boolean;
  isPolling: boolean;
  isSubmittingAnswers: boolean;
  isSubmittingDecision: boolean;
  onRefresh: () => void;
  onStageDecision: (stageKey: string, payload: StageDecisionRequest) => Promise<void>;
  onSubmitIntakeAnswers: (intakeRunId: string, answers: IntakeAnswer[]) => Promise<void>;
  project: ProjectDetailResponse | null;
  projectState: ProjectStateResponse | null;
};

const statusLabels: Record<string, string> = {
  QUEUED: "排队中",
  RUNNING: "生成中",
  SUCCEEDED: "已完成",
  FAILED: "失败",
  WAITING_USER: "等待选择",
};

const WORKBENCH_STAGES: WorkbenchStage[] = [
  "DIRECTIONS",
  "LOGO",
  "IP",
];

const stageActionLabels: Record<WorkbenchStage, string> = {
  DIRECTIONS: "选择方向并生成 Logo",
  LOGO: "选择 Logo 并生成 IP",
  IP: "确认 IP 并完成项目",
};

function isIntakeResult(result: StageRunDetailResponse["result"]): result is IntakeResult {
  return Boolean(
    result &&
      typeof result === "object" &&
      "ready" in result &&
      "questions" in result &&
      Array.isArray(result.questions),
  );
}

function formatJsonValue(value: JsonValue | undefined) {
  if (value === undefined || value === null || value === "") {
    return "未填写";
  }
  if (Array.isArray(value)) {
    return value.length > 0 ? value.join("、") : "未填写";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function stageKey(stage: string) {
  return stage.toLowerCase();
}

function isRecord(value: unknown): value is Record<string, JsonValue> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function getStageDecision(
  decisions: DecisionStateResponse[],
  stage: string,
): DecisionStateResponse | undefined {
  return [...decisions].reverse().find((decision) => decision.stage === stage);
}

function isConfirmingDecision(decision: DecisionStateResponse | undefined) {
  return Boolean(
    decision &&
      (decision.action === "SELECT_VERSION" ||
        decision.action === "CONFIRM_VERSION" ||
        decision.action === "SKIP"),
  );
}

function buildStageSummaries(state: ProjectStateResponse): WorkbenchStageSummary[] {
  return WORKBENCH_STAGES.map((stage) => {
    const version = state.versions[stage];
    const run = state.stage_runs[stage];
    const decision = getStageDecision(state.decisions, stage);
    let status: WorkbenchStageSummary["status"] = "LOCKED";

    if (version?.status === "STALE") {
      status = "STALE";
    } else if (run?.status === "QUEUED" || run?.status === "RUNNING") {
      status = "GENERATING";
    } else if (isConfirmingDecision(decision)) {
      status = "CONFIRMED";
    } else if (version?.status === "GENERATED" || run?.status === "WAITING_USER") {
      status = "AWAITING_DECISION";
    }

    return {
      stage,
      status,
      version_id: version?.id ?? null,
      selected_item_id: decision?.selected_item_id ?? null,
    };
  });
}

function renderValue(value: JsonValue, depth = 0): string {
  if (value === null) {
    return "无";
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "无";
    }
    if (value.every((item) => typeof item !== "object" || item === null)) {
      return value.map((item) => String(item)).join("、");
    }
    return value
      .slice(0, depth > 0 ? 2 : 4)
      .map((item) => renderValue(item, depth + 1))
      .join(" / ");
  }
  if (typeof value === "object") {
    return Object.entries(value)
      .slice(0, depth > 0 ? 4 : 6)
      .map(([key, item]) => `${key}: ${renderValue(item, depth + 1)}`)
      .join("；");
  }
  return String(value);
}

function outputSummary(output: Record<string, JsonValue>) {
  return Object.entries(output)
    .filter(([key]) => key !== "schema_version")
    .slice(0, 8);
}

function StageRunTimeline({ runs }: { runs: StageRunResponse[] }) {
  if (runs.length === 0) {
    return <EmptyState title="暂无任务">创建项目后会出现 Intake Run。</EmptyState>;
  }

  return (
    <ol className="run-list">
      {runs.map((run) => (
        <li key={run.id}>
          <span>
            <strong>{run.stage}</strong>
            <small>{run.id}</small>
          </span>
          <em className={`run-status run-status--${run.status.toLowerCase()}`}>
            {statusLabels[run.status] ?? run.status}
          </em>
        </li>
      ))}
    </ol>
  );
}

function ActiveRunPanel({
  activeRun,
  isPolling,
  isSubmittingAnswers,
  onSubmitIntakeAnswers,
}: Pick<
  ProjectDetailProps,
  "activeRun" | "isPolling" | "isSubmittingAnswers" | "onSubmitIntakeAnswers"
>) {
  if (!activeRun) {
    return <EmptyState title="暂无当前任务">请选择项目或创建新项目。</EmptyState>;
  }

  if (activeRun.status === "QUEUED" || activeRun.status === "RUNNING") {
    return (
      <LoadingState
        title={`${activeRun.stage} ${statusLabels[activeRun.status] ?? activeRun.status}`}
      />
    );
  }

  if (activeRun.status === "FAILED") {
    return (
      <ErrorState title={`${activeRun.stage} 任务失败`}>
        {activeRun.error_message ?? activeRun.error_code ?? "后端未返回错误信息。"}
      </ErrorState>
    );
  }

  if (activeRun.stage === "INTAKE" && isIntakeResult(activeRun.result)) {
    if (!activeRun.result.ready) {
      return (
        <IntakeQuestions
          key={`${activeRun.id}:${activeRun.result.questions
            .map((question) => question.id)
            .join("|")}`}
          intakeRunId={activeRun.id}
          isSubmitting={isSubmittingAnswers}
          onSubmit={onSubmitIntakeAnswers}
          result={activeRun.result}
        />
      );
    }

    return (
      <div className="success-panel">
        <span className="step-pill">Intake 完成</span>
        <h2>品牌信息已满足生成条件</h2>
        <p>当前 Intake Run 已成功完成。</p>
      </div>
    );
  }

  if (activeRun.stage === "DIRECTIONS" && activeRun.status === "SUCCEEDED") {
    return (
      <div className="success-panel">
        <span className="step-pill">品牌方向</span>
        <h2>品牌方向已生成</h2>
        <p>结果版本：{activeRun.result_version_id ?? "后端未返回版本 ID"}</p>
        <p>下一步可以进入品牌方向选择。</p>
      </div>
    );
  }

  return (
    <div className="success-panel">
      <span className="step-pill">{activeRun.stage}</span>
      <h2>{statusLabels[activeRun.status] ?? activeRun.status}</h2>
      {isPolling ? <p>正在同步最新状态。</p> : null}
    </div>
  );
}

function buildLogoAssetUrls(projectId: string, output: LogoOutput): Record<string, string> {
  return Object.fromEntries(
    (output.concepts ?? []).map((concept) => [
      concept.preview_asset_id,
      apiClient.getProjectAssetUrl(projectId, concept.preview_asset_id),
    ]),
  );
}

function GenericStagePanel({
  isSubmitting,
  isProjectCompleted,
  onConfirm,
  stage,
  status,
  version,
}: {
  isSubmitting: boolean;
  isProjectCompleted: boolean;
  onConfirm: () => void;
  stage: WorkbenchStage;
  status: WorkbenchStageStatus;
  version: StageVersionStateResponse;
}) {
  const canConfirm = status === "AWAITING_DECISION" && !isProjectCompleted;
  const buttonLabel =
    isSubmitting && canConfirm
      ? "提交中"
      : status === "CONFIRMED" || isProjectCompleted
        ? "已确认"
        : status === "GENERATING"
          ? "生成中"
          : status === "LOCKED"
            ? "未解锁"
            : status === "STALE"
              ? "需更新"
              : stageActionLabels[stage];

  return (
    <section className="stage-result-panel">
      <header className="section-header">
        <span className="step-pill">{stage}</span>
        <h2>{stageActionLabels[stage]}</h2>
        <p>版本 {version.version_no} · {version.id}</p>
      </header>

      <div className="result-summary-grid">
        {outputSummary(version.output).map(([key, value]) => (
          <article className="result-summary-card" key={`${stage}-${key}`}>
            <span>{key}</span>
            <p>{renderValue(value)}</p>
          </article>
        ))}
      </div>

      <div className="stage-actions">
        <Button disabled={!canConfirm || isSubmitting} onClick={onConfirm}>
          {buttonLabel}
        </Button>
      </div>
    </section>
  );
}

function CompletedExportPanel({ projectId }: { projectId: string }) {
  return (
    <section className="stage-result-panel">
      <header className="section-header">
        <span className="step-pill">COMPLETED</span>
        <h2>项目已完成</h2>
        <p>可以下载 Markdown 交付说明或 ZIP 交付包。</p>
      </header>
      <div className="stage-actions">
        <a className="ui-button ui-button--primary download-link" href={`/api/v1/projects/${projectId}/exports/proposal.md`}>
          下载 Markdown
        </a>
        <a className="ui-button ui-button--secondary download-link" href={`/api/v1/projects/${projectId}/exports/proposal.zip`}>
          下载 ZIP
        </a>
      </div>
    </section>
  );
}

function WorkbenchPanel({
  isSubmittingDecision,
  onStageDecision,
  projectState,
}: Pick<
  ProjectDetailProps,
  "isSubmittingDecision" | "onStageDecision" | "projectState"
>) {
  if (!projectState) {
    return null;
  }

  const stages = buildStageSummaries(projectState);
  const isProjectCompleted = projectState.project.status === "COMPLETED";
  const directionsVersion = projectState.versions.DIRECTIONS;
  const logoVersion = projectState.versions.LOGO;
  const directionsSummary = stages.find((stage) => stage.stage === "DIRECTIONS");
  const logoSummary = stages.find((stage) => stage.stage === "LOGO");

  function handleSelect(selection: VersionItemSelection) {
    void onStageDecision(stageKey(selection.stage), {
      action: "SELECT_VERSION",
      version_id: selection.version_id,
      selected_item_id: selection.item_id,
    });
  }

  function handleConfirm(stage: WorkbenchStage, versionId: string) {
    void onStageDecision(stageKey(stage), {
      action: "CONFIRM_VERSION",
      version_id: versionId,
      confirmed: true,
    });
  }

  return (
    <section className="workbench-panel">
      <aside className="workbench-stage-list">
        <StageNavigation stages={stages} />
      </aside>

      <div className="workbench-stage-content">
        {directionsVersion && isRecord(directionsVersion.output) ? (
          <section className="stage-result-panel">
            <header className="section-header">
              <span className="step-pill">DIRECTIONS</span>
              <h2>艺术总监 Agent：品牌方向</h2>
              <p>选择一个方向后会排队生成 Logo。</p>
            </header>
            <DirectionsResult
              isDisabled={
                isSubmittingDecision ||
                isProjectCompleted ||
                directionsSummary?.status !== "AWAITING_DECISION"
              }
              onSelect={handleSelect}
              output={directionsVersion.output as DirectionOutput}
              selectedDirectionId={directionsSummary?.selected_item_id}
              versionId={directionsVersion.id}
            />
          </section>
        ) : null}

        {logoVersion && isRecord(logoVersion.output) ? (
          <section className="stage-result-panel">
            <header className="section-header">
              <span className="step-pill">LOGO</span>
              <h2>Logo Agent：Logo 方案</h2>
              <p>选择一个 Logo 后会排队生成 IP 形象。</p>
            </header>
            <LogoResult
              assetUrls={buildLogoAssetUrls(
                projectState.project.id,
                logoVersion.output as LogoOutput,
              )}
              isDisabled={
                isSubmittingDecision ||
                isProjectCompleted ||
                logoSummary?.status !== "AWAITING_DECISION"
              }
              onSelect={handleSelect}
              output={logoVersion.output as LogoOutput}
              selectedLogoId={logoSummary?.selected_item_id}
              versionId={logoVersion.id}
            />
          </section>
        ) : null}

        {WORKBENCH_STAGES.filter((stage) => !["DIRECTIONS", "LOGO"].includes(stage)).map((stage) => {
          const version = projectState.versions[stage];
          const summary = stages.find((item) => item.stage === stage);
          if (!version) {
            return null;
          }
          return (
            <GenericStagePanel
              isSubmitting={isSubmittingDecision}
              isProjectCompleted={isProjectCompleted}
              key={stage}
              onConfirm={() => handleConfirm(stage, version.id)}
              stage={stage}
              status={summary?.status ?? "LOCKED"}
              version={version}
            />
          );
        })}

        {isProjectCompleted ? (
          <CompletedExportPanel projectId={projectState.project.id} />
        ) : null}
      </div>
    </section>
  );
}

export function ProjectDetail({
  activeRun,
  isLoading,
  isPolling,
  isSubmittingAnswers,
  isSubmittingDecision,
  onRefresh,
  onStageDecision,
  onSubmitIntakeAnswers,
  project,
  projectState,
}: ProjectDetailProps) {
  if (isLoading) {
    return <LoadingState title="正在读取项目详情" />;
  }

  if (!project) {
    return <EmptyState title="请选择项目">左侧选择已有项目，或创建一个新项目。</EmptyState>;
  }

  return (
    <div className="detail-layout">
      <section className="detail-main">
        <header className="project-heading">
          <span className="step-pill">{project.current_stage}</span>
          <h1>{project.name}</h1>
          <p>
            项目状态：{project.status} · 版本 {project.version}
          </p>
          <Button onClick={onRefresh} variant="secondary">
            刷新状态
          </Button>
        </header>

        <ActiveRunPanel
          activeRun={activeRun}
          isPolling={isPolling}
          isSubmittingAnswers={isSubmittingAnswers}
          onSubmitIntakeAnswers={onSubmitIntakeAnswers}
        />

        <WorkbenchPanel
          isSubmittingDecision={isSubmittingDecision}
          onStageDecision={onStageDecision}
          projectState={projectState}
        />
      </section>

      <aside className="detail-side">
        <section className="side-section">
          <h2>BrandSpec</h2>
          <dl className="spec-list">
            {BRAND_SPEC_FIELDS.map((field) => (
              <div key={field.key}>
                <dt>{field.label}</dt>
                <dd>{formatJsonValue(project.brand_spec[field.key])}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="side-section">
          <h2>Stage Runs</h2>
          <StageRunTimeline runs={project.stage_runs} />
        </section>
      </aside>
    </div>
  );
}
