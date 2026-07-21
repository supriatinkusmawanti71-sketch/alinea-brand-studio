import type { WorkbenchStage, WorkbenchStageSummary } from "@/features/workbench/types";

import styles from "./stage-navigation.module.css";

const stageLabels: Record<WorkbenchStage, string> = {
  DIRECTIONS: "艺术总监",
  LOGO: "Logo Agent",
  IP: "IP 设计师",
};

const statusLabels: Record<WorkbenchStageSummary["status"], string> = {
  LOCKED: "未解锁",
  GENERATING: "生成中",
  AWAITING_DECISION: "待选择",
  CONFIRMED: "已确认",
  STALE: "需更新",
};

const statusClassNames: Record<WorkbenchStageSummary["status"], string> = {
  LOCKED: styles.locked,
  GENERATING: styles.generating,
  AWAITING_DECISION: styles.awaitingDecision,
  CONFIRMED: styles.confirmed,
  STALE: styles.stale,
};

type StageNavigationProps = {
  stages: WorkbenchStageSummary[];
};

export function StageNavigation({ stages }: StageNavigationProps) {
  return (
    <nav aria-label="品牌生成阶段" className={styles.nav}>
      {stages.map((stage) => (
        <div
          className={`${styles.item} ${statusClassNames[stage.status]}`}
          key={stage.stage}
        >
          <span className={styles.dot} />
          <span className={styles.body}>
            <strong className={styles.name}>{stageLabels[stage.stage]}</strong>
            <span className={styles.meta}>
              {stage.version_id ? `version ${stage.version_id}` : "N/A"}
            </span>
          </span>
          <span className={styles.badge}>{statusLabels[stage.status]}</span>
        </div>
      ))}
    </nav>
  );
}
