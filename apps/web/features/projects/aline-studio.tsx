"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { apiClient, ApiError } from "@/lib/api/client";
import { pollStageRun } from "@/lib/api/polling";
import type {
  IntakeQuestion,
  IntakeResult,
  JsonValue,
  ProjectResponse,
  ProjectStateResponse,
  StageRunDetailResponse,
} from "@/lib/api/types";

import styles from "./aline-studio.module.css";

const runningStatuses = new Set(["QUEUED", "RUNNING"]);
const redoableStages = new Set<AgentKey>(["DIRECTIONS", "LOGO", "IP"]);

type PageMode = "home" | "workspace";
type AgentKey = "DIRECTIONS" | "LOGO" | "IP";

type AgentStep = {
  key: AgentKey;
  role: string;
  title: string;
  state: string;
  action: string;
  pending: string[];
  done: string[];
};

const agents: AgentStep[] = [
  {
    key: "DIRECTIONS",
    role: "艺术总监",
    title: "艺术总监生成品牌方向",
    state: "生成 3 个品牌方向中",
    action: "选择方向并生成 Logo",
    pending: ["拆解品牌需求", "生成 3 个差异化方向", "生成 3 张方向预览图"],
    done: ["3 个品牌方向已生成", "选择其中一个方向后进入 Logo Agent"],
  },
  {
    key: "LOGO",
    role: "Logo 设计师",
    title: "Logo 设计师生成方案",
    state: "生成 4 个 Logo 方案中",
    action: "选择 Logo 并生成 IP",
    pending: ["继承已选品牌方向", "生成 4 个 Logo 概念", "生成 4 张 Logo 图"],
    done: ["4 个 Logo 方案已生成", "选择其中一个 Logo 后进入 IP 设计师 Agent"],
  },
  {
    key: "IP",
    role: "IP 设计师",
    title: "IP 设计师生成品牌形象",
    state: "生成 1 个 IP 主形象中",
    action: "确认 IP 并完成项目",
    pending: ["继承已选品牌方向和 Logo", "生成 1 个 IP 主形象", "确认后可下载交付包"],
    done: ["IP 主形象已生成", "确认后导出 Logo 与 IP 交付包"],
  },
];

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return "发生未知错误";
}

function stageIndex(stage: string | null | undefined) {
  const index = agents.findIndex((agent) => agent.key === stage);
  return index >= 0 ? index : 0;
}

function makeProjectName(prompt: string) {
  const match = prompt.match(/(?:品牌名|名称)[:：]\s*([^，。,\n]+)/);
  if (match?.[1]) {
    return match[1].trim().slice(0, 40);
  }
  const called = prompt.match(/叫\s*([A-Za-z0-9\u4e00-\u9fa5_-]{1,40})/);
  if (called?.[1]) {
    return called[1].trim().slice(0, 40);
  }
  return prompt.replace(/\s+/g, " ").slice(0, 24) || "品牌形象项目";
}

function inferIndustry(prompt: string) {
  if (/面包|烘焙|蛋糕|甜品|糕点/.test(prompt)) {
    return "烘焙/食品";
  }
  if (/茶|奶茶|饮品/.test(prompt)) {
    return "茶饮";
  }
  if (/咖啡/.test(prompt)) {
    return "咖啡";
  }
  if (/护肤|美妆|香氛/.test(prompt)) {
    return "美妆个护";
  }
  if (/餐厅|餐饮|小吃/.test(prompt)) {
    return "餐饮";
  }
  return "消费品牌";
}

function buildStructuredFields(prompt: string) {
  const industry = inferIndustry(prompt);
  const foodAudience = industry === "烘焙/食品" || industry === "餐饮";
  const beverageAudience = industry === "茶饮" || industry === "咖啡";
  return {
    industry,
    brand_background: prompt,
    target_audiences: foodAudience
      ? ["关注新鲜口感和生活品质的城市消费者"]
      : beverageAudience
        ? ["重视日常体验和品质感的城市消费者"]
        : ["关注品质、审美和清晰品牌识别的目标用户"],
    price_positioning: "中端日常消费",
    brand_personality: ["温暖", "可信", "有识别度"],
    style_keywords: ["现代", "简洁", "温暖", "高识别度"],
    required_elements: ["品牌方向", "Logo方案", "IP主形象"],
    prohibited_elements: ["侵权元素", "不可商用承诺", "过度复杂细节"],
    language: "zh-CN",
  };
}

function latestDecision(state: ProjectStateResponse | null, stage: AgentKey) {
  return [...(state?.decisions ?? [])].reverse().find((decision) => decision.stage === stage);
}

function stageKeyPath(stage: AgentKey) {
  return stage.toLowerCase();
}

function stageRunDetailFromState(
  run: ProjectStateResponse["stage_runs"][string] | undefined,
): StageRunDetailResponse | null {
  if (!run) {
    return null;
  }
  return { ...run, result: null };
}

function latestStageRunFromState(state: ProjectStateResponse) {
  const runs = Object.values(state.stage_runs);
  const runningRun = runs
    .filter((run) => runningStatuses.has(run.status))
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0];
  if (runningRun) {
    return stageRunDetailFromState(runningRun);
  }
  return stageRunDetailFromState(
    state.stage_runs[state.current_stage] ??
    runs.sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0],
  );
}

function imageUrl(project: ProjectResponse | null, assetId: string | undefined) {
  if (!project || !assetId) {
    return "";
  }
  return apiClient.getProjectAssetUrl(project.id, assetId);
}

function downloadUrl(project: ProjectResponse | null, assetId: string | undefined, filename: string) {
  const base = imageUrl(project, assetId);
  if (!base) {
    return "";
  }
  return `${base}?download=true&filename=${encodeURIComponent(filename)}`;
}

function intakeResultFrom(value: unknown): IntakeResult | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  if (typeof record.ready !== "boolean" || !Array.isArray(record.questions)) {
    return null;
  }
  return record as IntakeResult;
}

function pendingIntakeQuestions(
  run: StageRunDetailResponse | null,
  state: ProjectStateResponse | null,
) {
  const result = intakeResultFrom(run?.stage === "INTAKE" ? run.result : undefined)
    ?? intakeResultFrom(state?.versions.INTAKE?.output);
  if (!result || result.ready) {
    return [];
  }
  return result.questions ?? [];
}

function answerValueFor(question: IntakeQuestion, text: string): JsonValue {
  const value = text.trim();
  if (question.answer_type === "TEXT_LIST" || question.answer_type === "MULTI_CHOICE") {
    const items = value
      .split(/[\n,，、；;]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    return items.length ? items : [value];
  }
  return value;
}

function runFailureMessage(run: StageRunDetailResponse | null, state: ProjectStateResponse | null) {
  const failedRun = run?.status === "FAILED"
    ? run
    : Object.values(state?.stage_runs ?? {}).find((item) => item.status === "FAILED");
  if (!failedRun) {
    return null;
  }
  return `${failedRun.stage} 生成失败：${failedRun.error_message ?? failedRun.error_code ?? "请补充更具体需求后重试"}`;
}

function progressInWindow(start: number, end: number, tick: number) {
  const ratio = Math.min(0.92, 0.18 + tick * 0.035);
  return Math.round(start + (end - start) * ratio);
}

function stageRunDetail(run: StageRunDetailResponse | null) {
  if (!run || !runningStatuses.has(run.status)) {
    return "";
  }
  if (run.status === "QUEUED") {
    return run.error_message || "任务已进入后台队列，正在等待 Agent 接手。";
  }
  const attempt = Math.max(run.attempt || 1, 1);
  if (run.stage === "DIRECTIONS") {
    return `艺术总监第 ${attempt} 次执行中，正在生成 3 张方向图。`;
  }
  if (run.stage === "LOGO") {
    return `Logo Agent 第 ${attempt} 次执行中，正在生成 4 张 Logo 图。`;
  }
  if (run.stage === "IP") {
    return `IP 设计师第 ${attempt} 次执行中，正在生成 1 张主形象图。`;
  }
  return `Agent 第 ${attempt} 次执行中。`;
}

function buildProgressSnapshot({
  activeRun,
  intakeQuestionCount,
  progressTick,
  project,
  projectState,
}: {
  activeRun: StageRunDetailResponse | null;
  intakeQuestionCount: number;
  progressTick: number;
  project: ProjectResponse | null;
  projectState: ProjectStateResponse | null;
}) {
  if (!project) {
    return { label: "准备开始", value: 0, detail: "输入品牌需求后开始三 Agent 流程。" };
  }
  if (project.status === "COMPLETED") {
    return { label: "已完成", value: 100, detail: "Logo 与 IP 交付包已可下载。" };
  }

  const failedRun = activeRun?.status === "FAILED"
    ? activeRun
    : Object.values(projectState?.stage_runs ?? {}).find((run) => run.status === "FAILED");
  if (failedRun) {
    const fallback = failedRun.stage === "LOGO" ? 34 : failedRun.stage === "IP" ? 67 : 12;
    return {
      label: `${failedRun.stage} 失败`,
      value: fallback,
      detail: failedRun.error_message ?? failedRun.error_code ?? "当前阶段未成功完成。",
    };
  }

  if (activeRun && runningStatuses.has(activeRun.status)) {
    if (activeRun.stage === "INTAKE") {
      return { label: "需求分析中", value: progressInWindow(4, 12, progressTick), detail: stageRunDetail(activeRun) };
    }
    if (activeRun.stage === "DIRECTIONS") {
      return { label: "艺术总监生成方向图", value: progressInWindow(14, 33, progressTick), detail: stageRunDetail(activeRun) };
    }
    if (activeRun.stage === "LOGO") {
      return { label: "Logo 设计师生成 4 张图", value: progressInWindow(42, 66, progressTick), detail: stageRunDetail(activeRun) };
    }
    if (activeRun.stage === "IP") {
      return { label: "IP 设计师生成主形象", value: progressInWindow(76, 94, progressTick), detail: stageRunDetail(activeRun) };
    }
  }

  if (intakeQuestionCount > 0) {
    return { label: "等待补充信息", value: 12, detail: "补充左侧问题后，艺术总监会继续生成方向。" };
  }
  if (projectState?.versions.IP) {
    return { label: "IP 已生成，等待确认", value: 94, detail: "确认 IP 后即可导出交付包。" };
  }
  if (projectState?.versions.LOGO) {
    return { label: "Logo 已生成，等待选择", value: 66, detail: "选择一个 Logo 后进入 IP 设计师 Agent。" };
  }
  if (projectState?.versions.DIRECTIONS) {
    return { label: "方向已生成，等待选择", value: 33, detail: "选择一个品牌方向后进入 Logo Agent。" };
  }
  if (projectState?.versions.INTAKE) {
    return { label: "需求分析完成", value: 12, detail: "品牌需求已结构化，准备进入艺术总监阶段。" };
  }
  return { label: project.status, value: 2, detail: "项目已创建，等待后台任务返回。" };
}

export function AlineStudio() {
  const promptInputRef = useRef<HTMLTextAreaElement | null>(null);
  const chatInputRef = useRef<HTMLTextAreaElement | null>(null);
  const [mode, setMode] = useState<PageMode>("home");
  const [prompt, setPrompt] = useState("");
  const [chatText, setChatText] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [projectState, setProjectState] = useState<ProjectStateResponse | null>(null);
  const [activeRun, setActiveRun] = useState<StageRunDetailResponse | null>(null);
  const [pollingRunId, setPollingRunId] = useState<string | null>(null);
  const [progressTick, setProgressTick] = useState(0);
  const [isBusy, setIsBusy] = useState(false);
  const [recentProject, setRecentProject] = useState<ProjectResponse | null>(null);

  const intakeQuestions = useMemo(
    () => pendingIntakeQuestions(activeRun, projectState),
    [activeRun, projectState],
  );

  const activeStepIndex = useMemo(() => {
    if (project?.status === "COMPLETED") {
      return 2;
    }
    if (activeRun && runningStatuses.has(activeRun.status)) {
      return stageIndex(activeRun.stage);
    }
    if (projectState?.versions.IP) {
      return 2;
    }
    if (projectState?.versions.LOGO) {
      return 1;
    }
    return 0;
  }, [activeRun, project, projectState]);

  const progress = useMemo(
    () => buildProgressSnapshot({
      activeRun,
      intakeQuestionCount: intakeQuestions.length,
      progressTick,
      project,
      projectState,
    }),
    [activeRun, intakeQuestions.length, progressTick, project, projectState],
  );

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 2600);
  }, []);

  const refreshState = useCallback(async (projectId: string) => {
    const nextState = await apiClient.getProjectState(projectId);
    setProjectState(nextState);
    setProject(nextState.project);
    setRecentProject(nextState.project);
    return nextState;
  }, []);

  const openProject = useCallback(async (projectId: string) => {
    setIsBusy(true);
    setErrorMessage(null);
    try {
      const state = await refreshState(projectId);
      const background = state.brand_spec.brand_background;
      setPrompt(typeof background === "string" ? background : state.project.name);
      setChatText("");
      setMode("workspace");
      const latestRun = latestStageRunFromState(state);
      setActiveRun(latestRun);
      setProgressTick(0);
      setPollingRunId(latestRun && runningStatuses.has(latestRun.status) ? latestRun.id : null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }, [refreshState]);

  const focusPromptInput = useCallback(() => {
    promptInputRef.current?.focus();
  }, []);

  const enterStudio = useCallback(() => {
    if (prompt.trim()) {
      void startProject();
      return;
    }
    if (recentProject) {
      void openProject(recentProject.id);
      return;
    }
    setMode("workspace");
    window.setTimeout(() => chatInputRef.current?.focus(), 0);
  }, [openProject, prompt, recentProject]);

  const resetToHome = useCallback(() => {
    setMode("home");
    setPrompt("");
    setChatText("");
    setErrorMessage(null);
    setProject(null);
    setProjectState(null);
    setActiveRun(null);
    setPollingRunId(null);
    setProgressTick(0);
    window.setTimeout(() => promptInputRef.current?.focus(), 0);
  }, []);

  const continueAfterRun = useCallback(async (run: StageRunDetailResponse) => {
    setActiveRun(run);
    const state = await refreshState(run.project_id);

    if (run.status === "FAILED") {
      setErrorMessage(runFailureMessage(run, state));
      return;
    }

    if (run.stage === "INTAKE" && run.status === "SUCCEEDED") {
      const intake = intakeResultFrom(run.result) ?? intakeResultFrom(state.versions.INTAKE?.output);
      if (intake && !intake.ready) {
        setErrorMessage(null);
        showToast("信息还不够完整，请在左侧补充后继续。");
        return;
      }
      const hasDirections = Boolean(state.stage_runs.DIRECTIONS);
      if (!hasDirections) {
        const resumed = await apiClient.submitIntakeAnswers(run.id, { answers: [] });
        setProgressTick(0);
        setPollingRunId(resumed.id);
      }
    }
  }, [refreshState, showToast]);

  useEffect(() => {
    let cancelled = false;
    apiClient.listProjects()
      .then((projects) => {
        if (!cancelled) {
          setRecentProject(projects[0] ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRecentProject(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!pollingRunId) {
      return;
    }

    const controller = new AbortController();
    pollStageRun(pollingRunId, {
      intervalMs: 2000,
      signal: controller.signal,
      onUpdate: setActiveRun,
    })
      .then((run) => {
        setPollingRunId(null);
        void continueAfterRun(run);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setPollingRunId(null);
          setErrorMessage(getErrorMessage(error));
        }
      });

    return () => controller.abort();
  }, [continueAfterRun, pollingRunId]);

  useEffect(() => {
    if (!pollingRunId) {
      return;
    }
    const interval = window.setInterval(() => {
      setProgressTick((current) => current + 1);
    }, 1500);
    return () => window.clearInterval(interval);
  }, [pollingRunId]);

  async function createProjectFromRequirement(requirementText: string) {
    const requirement = requirementText.trim();
    if (!requirement) {
      if (mode === "workspace") {
        chatInputRef.current?.focus();
      } else {
        focusPromptInput();
      }
      return;
    }
    setIsBusy(true);
    setErrorMessage(null);
    try {
      const created = await apiClient.createProject({
        name: makeProjectName(requirement),
        requirement_text: requirement,
        structured_fields: buildStructuredFields(requirement),
        reference_artifact_ids: [],
      });
      setPrompt(requirement);
      setProject(created.project);
      setRecentProject(created.project);
      setProjectState(null);
      setMode("workspace");
      setActiveRun({
        ...created.stage_run,
        error_message: null,
        result: null,
      });
      setProgressTick(0);
      setPollingRunId(created.stage_run.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function startProject() {
    await createProjectFromRequirement(prompt);
  }

  async function selectDirection(directionId: string) {
    if (!project || !projectState?.versions.DIRECTIONS) {
      return;
    }
    setIsBusy(true);
    try {
      const response = await apiClient.createStageDecision(project.id, "directions", {
        action: "SELECT_VERSION",
        version_id: projectState.versions.DIRECTIONS.id,
        selected_item_id: directionId,
      });
      await refreshState(project.id);
      setActiveRun({ ...response.stage_run, result: null });
      setProgressTick(0);
      setPollingRunId(response.stage_run.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function regenerateStage(stage: AgentKey) {
    if (!project || !projectState) {
      return;
    }
    if (!redoableStages.has(stage)) {
      showToast("当前阶段暂不支持重新生成，请重新选择上一步结果继续。");
      return;
    }
    const version = projectState.versions[stage];
    if (!version || version.status !== "GENERATED") {
      showToast("当前阶段还没有可重新生成的版本。");
      return;
    }
    setIsBusy(true);
    setErrorMessage(null);
    const feedback = chatText.trim();
    try {
      await apiClient.requestStageControl(project.id, stageKeyPath(stage), "redo", {
        source_version_id: version.id,
        reason: feedback || "用户在前端点击重新生成",
      });
      if (feedback) {
        setChatText("");
      }
      const state = await refreshState(project.id);
      const run = stageRunDetailFromState(state.stage_runs[stage]);
      setActiveRun(run);
      setProgressTick(0);
      setPollingRunId(run ? run.id : null);
      showToast(feedback ? "已带着你的反馈重新生成。" : "已重新投递，Agent 正在生成新结果。");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function selectLogo(logoId: string) {
    if (!project || !projectState?.versions.LOGO) {
      return;
    }
    setIsBusy(true);
    try {
      const response = await apiClient.createStageDecision(project.id, "logo", {
        action: "SELECT_VERSION",
        version_id: projectState.versions.LOGO.id,
        selected_item_id: logoId,
      });
      await refreshState(project.id);
      setActiveRun({ ...response.stage_run, result: null });
      setProgressTick(0);
      setPollingRunId(response.stage_run.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function confirmIp() {
    if (!project || !projectState?.versions.IP) {
      return;
    }
    setIsBusy(true);
    try {
      const response = await apiClient.createStageDecision(project.id, "ip", {
        action: "CONFIRM_VERSION",
        version_id: projectState.versions.IP.id,
        confirmed: true,
      });
      setActiveRun({ ...response.stage_run, result: null });
      await refreshState(project.id);
      showToast("品牌方向、Logo 与 IP 已完成，可以下载交付包。");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  function sendChatMessage() {
    void submitChatMessage();
  }

  async function submitChatMessage() {
    const text = chatText.trim();
    if (!text) {
      chatInputRef.current?.focus();
      return;
    }
    setChatText("");
    if (!project) {
      await createProjectFromRequirement(text);
      return;
    }
    if (project && activeRun?.stage === "INTAKE" && activeRun.status === "SUCCEEDED" && intakeQuestions.length) {
      setIsBusy(true);
      setErrorMessage(null);
      try {
        const response = await apiClient.submitIntakeAnswers(activeRun.id, {
          answers: intakeQuestions.map((question) => ({
            field_path: question.field_path,
            value: answerValueFor(question, text),
          })),
        });
        setActiveRun({
          id: response.id,
          project_id: response.project_id,
          stage: response.stage,
          status: response.status,
          attempt: 0,
          error_code: null,
          error_message: null,
          result_version_id: null,
          result: null,
        });
        setProgressTick(0);
        setPollingRunId(response.id);
      } catch (error) {
        setErrorMessage(getErrorMessage(error));
      } finally {
        setIsBusy(false);
      }
      return;
    }
    setPrompt((current) => `${current}\n${text}`.trim());
  }

  return (
    <main className={styles.app}>
      <div className={styles.frame}>
        {mode === "home" ? (
          <>
            <header className={styles.topbar}>
              <button className={styles.brand} onClick={enterStudio} type="button">
                <span className={styles.brandMark} />
                <span>
                  <strong>Alinea</strong>
                  <small>Brand Agent Studio</small>
                </span>
              </button>
              <button className={styles.profileButton} onClick={enterStudio} type="button" aria-label="进入工作台" />
            </header>
            <section className={styles.page}>
              <div className={styles.homeHero}>
                <div aria-hidden className={styles.heroLines}>
                  <span /><span /><span /><span /><span /><span />
                </div>
                <div className={styles.heroContent}>
                  <div className={styles.hello}>
                    <h1>
                      你好，<span className={styles.serifWord}>Alinea</span> 创作者
                    </h1>
                  </div>
                  <p className={styles.subline}>今天想把哪个想法变成方案？</p>
                  <div className={styles.composer}>
                    <textarea
                      ref={promptInputRef}
                      onChange={(event) => setPrompt(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                          void startProject();
                        }
                      }}
                      placeholder="输入你的品牌、活动、包装或视觉需求..."
                      value={prompt}
                    />
                    <div className={styles.composerBar}>
                      <div className={styles.toolRow}>
                        <span className={styles.chip}>品牌策略</span>
                        <span className={styles.chip}>Logo</span>
                        <span className={styles.chip}>IP</span>
                        <span className={`${styles.chip} ${styles.chipHot}`}>品牌形象</span>
                      </div>
                      <button
                        aria-label="开始生成"
                        className={styles.sendButton}
                        disabled={isBusy}
                        onClick={enterStudio}
                        title={prompt.trim() ? "开始生成" : recentProject ? "继续最近项目" : "进入创作"}
                        type="button"
                      >
                        {isBusy ? "…" : "↑"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <section className={styles.gallery}>
                <div className={styles.sectionHead}>
                  <h2>优秀案例</h2>
                  <span className={styles.chip}>全部 &gt;</span>
                </div>
                <div className={styles.caseRow}>
                  <button className={`${styles.caseCard} ${styles.caseStart}`} onClick={enterStudio} type="button">
                    <div>
                      <div className={styles.casePlus}>+</div>
                      <strong>{prompt.trim() ? "开始生成" : recentProject ? "继续最近项目" : "进入创作"}</strong>
                    </div>
                  </button>
                  {[
                    ["LUMA CAFE", "咖啡品牌 LUMA CAFE，现代、温暖、适合城市白领日常消费"],
                    ["NOVA GRID", "科技生活方式品牌 NOVA GRID，未来感、极简、高识别度"],
                    ["MORI SKIN", "护肤品牌 MORI SKIN，自然、干净、专业且有亲和力"],
                  ].map(([name, sample]) => (
                    <button className={styles.caseCard} key={name} onClick={() => {
                      setPrompt(sample);
                      promptInputRef.current?.focus();
                      showToast("案例需求已填入，可以点击右侧箭头开始生成。");
                    }} type="button">
                      <span className={styles.chip}>Identity</span>
                      <h3>{name}</h3>
                      <p>覆盖品牌方向、Logo 与 IP 角色的一站式生成流程。</p>
                    </button>
                  ))}
                </div>
              </section>
            </section>
          </>
        ) : (
          <section className={styles.workspace}>
            <div className={styles.workspaceTop}>
              <div className={styles.projectPill}>
                <div className={styles.projectLogo}><span className={styles.projectMark} /></div>
                <div className={styles.projectTitle}>{project?.name ?? "品牌形象项目"}</div>
              </div>
              <div className={styles.workspaceActions}>
                <button className={styles.ghostButton} onClick={resetToHome} type="button">新建项目</button>
                {project?.status === "COMPLETED" ? (
                  <>
                    <a className={`${styles.downloadButton} ${styles.downloadPrimary}`} href={apiClient.getProposalMarkdownUrl(project.id)}>下载 Markdown</a>
                    <a className={styles.downloadButton} href={apiClient.getProposalZipUrl(project.id)}>下载 ZIP</a>
                  </>
                ) : null}
              </div>
            </div>

            <div className={styles.workspaceGrid}>
              <aside className={styles.chatPanel}>
                <div className={styles.chatHead}>
                  <div className={styles.agentBadge}>Alinea Agent</div>
                  <span className={styles.chip}>{activeRun?.status ?? project?.status ?? "READY"}</span>
                </div>
                <div className={styles.messages}>
                  <div className={styles.userBubble}>{prompt || "等待输入品牌需求"}</div>
                  {intakeQuestions.length ? (
                    <div className={`${styles.agentMessage} ${styles.agentMessageCurrent}`}>
                      <div className={styles.agentName}>
                        <span className={styles.avatar}>?</span>
                        需求补充
                      </div>
                      <div className={styles.agentState}>需要补充信息</div>
                      <ul className={styles.agentCopy}>
                        {intakeQuestions.map((question) => <li key={question.id}>{question.prompt}</li>)}
                      </ul>
                    </div>
                  ) : null}
                  {runFailureMessage(activeRun, projectState) ? (
                    <div className={styles.statusAlert}>{runFailureMessage(activeRun, projectState)}</div>
                  ) : null}
                  {agents.map((agent, index) => {
                    const version = projectState?.versions[agent.key];
                    const isDone = Boolean(version) || project?.status === "COMPLETED";
                    const isCurrent = activeStepIndex === index && !isDone && !intakeQuestions.length;
                    return (
                      <div
                        className={`${styles.agentMessage} ${isCurrent ? styles.agentMessageCurrent : ""} ${isDone ? styles.agentMessageDone : ""}`}
                        key={agent.key}
                      >
                        <div className={styles.agentName}>
                          <span className={styles.avatar}>{index + 1}</span>
                          {agent.role}
                        </div>
                        <div className={styles.agentState}>{isDone ? "已生成" : isCurrent ? agent.state : "等待上一步确认"}</div>
                        <ul className={styles.agentCopy}>
                          {(isDone ? agent.done : agent.pending).map((line) => <li key={line}>{line}</li>)}
                        </ul>
                      </div>
                    );
                  })}
                </div>
                <div className={styles.chatInput}>
                  <div className={styles.chatComposer}>
                    <textarea
                      ref={chatInputRef}
                      onChange={(event) => setChatText(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                          void submitChatMessage();
                        }
                      }}
                      placeholder={!project ? "输入品牌需求，发送后开始三 Agent 流程..." : intakeQuestions.length ? "按上方问题补充信息，多个答案可用逗号分隔..." : "在这里写修改意见，再点击对应阶段的『重新生成』，Agent 会带着你的反馈重画..."}
                      value={chatText}
                    />
                    <div className={styles.chatTools}>
                      <div className={styles.toolRow}>
                        <span className={styles.chip}>Agent</span>
                        <span className={styles.chip}>资产</span>
                      </div>
                      <button aria-label="发送补充信息" className={styles.chatSend} disabled={isBusy} onClick={sendChatMessage} type="button">
                        {isBusy ? "…" : "●"}
                      </button>
                    </div>
                  </div>
                </div>
              </aside>

              <section className={styles.outputPanel}>
                <div className={styles.outputHeader}>
                  <div>
                    <h2>{agents[activeStepIndex]?.title ?? "品牌形象画布"}</h2>
                    <p>每个 Agent 确认后，内容会沉淀为品牌方向、Logo 与 IP 形象。图片质量由你最终判断。</p>
                    {errorMessage || runFailureMessage(activeRun, projectState) ? (
                      <p className={styles.error}>{errorMessage ?? runFailureMessage(activeRun, projectState)}</p>
                    ) : null}
                  </div>
                  <div className={styles.progress}>
                    <span>{progress.label} {progress.value}%</span>
                    <div className={styles.progressTrack}><div className={styles.progressFill} style={{ width: `${progress.value}%` }} /></div>
                    {progress.detail ? <small>{progress.detail}</small> : null}
                  </div>
                </div>
                <OutputBoard
                  confirmIp={confirmIp}
                  intakeQuestions={intakeQuestions}
                  isBusy={isBusy || Boolean(pollingRunId)}
                  project={project}
                  projectState={projectState}
                  regenerateStage={regenerateStage}
                  selectDirection={selectDirection}
                  selectLogo={selectLogo}
                />
              </section>
            </div>
          </section>
        )}
      </div>
      {toast ? <div className={styles.toast}>{toast}</div> : null}
    </main>
  );
}

function OutputBoard({
  confirmIp,
  intakeQuestions,
  isBusy,
  project,
  projectState,
  regenerateStage,
  selectDirection,
  selectLogo,
}: {
  confirmIp: () => Promise<void>;
  intakeQuestions: IntakeQuestion[];
  isBusy: boolean;
  project: ProjectResponse | null;
  projectState: ProjectStateResponse | null;
  regenerateStage: (stage: AgentKey) => Promise<void>;
  selectDirection: (directionId: string) => Promise<void>;
  selectLogo: (logoId: string) => Promise<void>;
}) {
  if (!projectState) {
    return (
      <div className={styles.emptyBoard}>
        {project
          ? "正在等待 Agent 输出。Intake 完成后会自动进入艺术总监阶段。"
          : "请在左侧输入品牌需求并发送，系统会自动进入艺术总监、Logo、IP 三 Agent 流程。"}
      </div>
    );
  }

  const directionsVersion = projectState.versions.DIRECTIONS?.status === "GENERATED" ? projectState.versions.DIRECTIONS : undefined;
  const logoVersion = projectState.versions.LOGO?.status === "GENERATED" ? projectState.versions.LOGO : undefined;
  const ipVersion = projectState.versions.IP?.status === "GENERATED" ? projectState.versions.IP : undefined;
  const directions = (directionsVersion?.output.directions as Record<string, JsonValue>[] | undefined) ?? [];
  const logos = (logoVersion?.output.concepts as Record<string, JsonValue>[] | undefined) ?? [];
  const ip = ipVersion?.output;
  const selectedDirection = latestDecision(projectState, "DIRECTIONS")?.selected_item_id;
  const selectedLogo = latestDecision(projectState, "LOGO")?.selected_item_id;
  const directionsRun = projectState.stage_runs.DIRECTIONS;
  const logoRun = projectState.stage_runs.LOGO;
  const ipRun = projectState.stage_runs.IP;

  if (intakeQuestions.length && !directions.length) {
    return (
      <StageBlock label="00 · 信息补齐" status="需要补充">
        <div className={styles.questionBoard}>
          <strong>艺术总监需要这些信息后再开始：</strong>
          <ul>
            {intakeQuestions.map((question) => <li key={question.id}>{question.prompt}</li>)}
          </ul>
          <p>请在左侧输入框一次性补充，多个答案可以用逗号分隔。</p>
        </div>
      </StageBlock>
    );
  }

  return (
    <>
      <StageBlock
        action={directions.length ? (
          <button className={styles.stageActionButton} disabled={isBusy} onClick={() => regenerateStage("DIRECTIONS")} type="button">
            重新生成
          </button>
        ) : null}
        label="01 · 艺术总监确认需求"
        status={directions.length ? "已生成" : directionsRun?.status === "FAILED" ? "失败" : "生成中"}
      >
        {directions.length ? (
          <div className={styles.contentGrid}>
            {directions.map((direction) => {
              const id = String(direction.id);
              return (
                <article className={`${styles.contentCard} ${selectedDirection === id ? styles.contentCardSelected : ""}`} key={id}>
                  <AssetDownload href={downloadUrl(project, String(direction.preview_asset_id), `品牌方向-${String(direction.name)}`)} />
                  <button disabled={isBusy || Boolean(selectedDirection)} onClick={() => selectDirection(id)} type="button">
                    <Visual alt={String(direction.name)} src={imageUrl(project, String(direction.preview_asset_id))} fallback="DIR" />
                  </button>
                </article>
              );
            })}
          </div>
        ) : (
          <div className={styles.emptyBoard}>
            {directionsRun?.status === "FAILED"
              ? `艺术总监生成失败：${directionsRun.error_message ?? directionsRun.error_code ?? "请补充更具体的需求后重新开始"}`
              : "艺术总监正在生成 3 个方向和 3 张方向图。图片生成可能需要几分钟。"}
          </div>
        )}
      </StageBlock>

      <StageBlock
        action={logos.length ? (
          <button className={styles.stageActionButton} disabled={isBusy} onClick={() => regenerateStage("LOGO")} type="button">
            重新生成
          </button>
        ) : null}
        label="02 · Logo 设计师生成方案"
        status={logos.length ? "已生成" : logoRun?.status === "FAILED" ? "失败" : selectedDirection ? "生成中" : "等待方向"}
      >
        {logos.length ? (
          <div className={`${styles.contentGrid} ${styles.contentGridFour}`}>
            {logos.map((logo) => {
              const id = String(logo.id);
              return (
                <article className={`${styles.contentCard} ${selectedLogo === id ? styles.contentCardSelected : ""}`} key={id}>
                  <AssetDownload href={downloadUrl(project, String(logo.preview_asset_id), `Logo方案-${String(logo.name)}`)} />
                  <button disabled={isBusy || Boolean(selectedLogo)} onClick={() => selectLogo(id)} type="button">
                    <Visual alt={String(logo.name)} src={imageUrl(project, String(logo.preview_asset_id))} fallback="LOGO" />
                  </button>
                </article>
              );
            })}
          </div>
        ) : (
          <div className={styles.emptyBoard}>
            {logoRun?.status === "FAILED"
              ? `Logo 生成失败：${logoRun.error_message ?? logoRun.error_code ?? "请换一个方向或重新生成"}`
              : "选择方向后，Logo Agent 会生成 4 个 Logo 方案。"}
          </div>
        )}
      </StageBlock>

      <StageBlock
        action={ip ? (
          <>
            <button className={styles.stageActionButton} disabled={isBusy} onClick={() => regenerateStage("IP")} type="button">
              重新生成
            </button>
            {project?.status !== "COMPLETED" ? (
              <button className={`${styles.stageActionButton} ${styles.stageActionButtonPrimary}`} disabled={isBusy} onClick={confirmIp} type="button">
                确认 IP
              </button>
            ) : null}
          </>
        ) : null}
        label="03 · IP 设计师生成品牌形象"
        status={ip ? "已生成" : ipRun?.status === "FAILED" ? "失败" : selectedLogo ? "生成中" : "等待 Logo"}
      >
        {ip ? (
          <div className={styles.contentGrid}>
            <article className={`${styles.contentCard} ${styles.contentCardSelected}`}>
              <AssetDownload href={downloadUrl(project, String(ip.preview_asset_id), "IP形象-主形象")} />
              <Visual alt="IP 主形象" src={imageUrl(project, String(ip.preview_asset_id))} fallback="IP" />
            </article>
            {((ip.views as Record<string, JsonValue>[] | undefined) ?? []).map((view) => (
              <article className={styles.contentCard} key={String(view.preview_asset_id)}>
                <AssetDownload href={downloadUrl(project, String(view.preview_asset_id), `IP形象-${String(view.name)}`)} />
                <Visual
                  alt={`IP ${String(view.name)}视图`}
                  src={imageUrl(project, String(view.preview_asset_id))}
                  fallback="IP"
                />
              </article>
            ))}
          </div>
        ) : (
          <div className={styles.emptyBoard}>
            {ipRun?.status === "FAILED"
              ? `IP 生成失败：${ipRun.error_message ?? ipRun.error_code ?? "请换一个 Logo 或重新生成"}`
              : "选择 Logo 后，IP 设计师会生成 IP 主形象和侧面、背面三视图。"}
          </div>
        )}
      </StageBlock>
    </>
  );
}

function StageBlock({
  action,
  children,
  label,
  status,
}: {
  action?: ReactNode;
  children: ReactNode;
  label: string;
  status: string;
}) {
  return (
    <section className={styles.stageBlock}>
      <div className={styles.stageTitle}>
        <strong>{label}</strong>
        <div className={styles.stageTitleActions}>
          {action}
          <span>{status}</span>
        </div>
      </div>
      {children}
    </section>
  );
}

function Visual({ alt, fallback, src }: { alt: string; fallback: string; src: string }) {
  return (
    <div className={styles.visual}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {src ? <img alt={alt} src={src} /> : <span className={styles.visualFallback}>{fallback}</span>}
    </div>
  );
}

function AssetDownload({ href }: { href: string }) {
  if (!href) {
    return null;
  }
  return (
    <a
      className={styles.assetDownload}
      href={href}
      onClick={(event) => event.stopPropagation()}
      title="下载这张图"
    >
      下载
    </a>
  );
}
