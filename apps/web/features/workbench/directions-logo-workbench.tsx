"use client";

import { useState } from "react";

import { StageNavigation } from "@/components/workbench/stage-navigation";
import { DirectionsResult } from "@/features/directions/directions-result";
import type { DirectionOutput } from "@/features/directions/types";
import { LogoResult } from "@/features/logo/logo-result";
import type { LogoOutput } from "@/features/logo/types";

import type { VersionItemSelection, WorkbenchStageSummary } from "./types";
import styles from "./directions-logo-workbench.module.css";

type DirectionsLogoWorkbenchProps = {
  assetUrls?: Record<string, string>;
  directions?: {
    output: DirectionOutput;
    version_id: string;
    selected_item_id?: string | null;
  } | null;
  logo?: {
    output: LogoOutput;
    version_id: string;
    selected_item_id?: string | null;
  } | null;
  stages: WorkbenchStageSummary[];
  onSelect: (selection: VersionItemSelection) => void;
};

export function DirectionsLogoWorkbench({
  assetUrls = {},
  directions,
  logo,
  stages,
  onSelect,
}: DirectionsLogoWorkbenchProps) {
  const [pendingSelection, setPendingSelection] = useState<VersionItemSelection | null>(null);

  function handleSelect(selection: VersionItemSelection) {
    setPendingSelection(selection);
    onSelect(selection);
  }

  return (
    <section className={styles.shell}>
      <aside className={styles.sidebar}>
        <StageNavigation stages={stages} />
      </aside>

      <div className={styles.content}>
        <section className={styles.panel}>
          <PanelHeader title="Directions" versionId={directions?.version_id} />
          {directions ? (
            <DirectionsResult
              onSelect={handleSelect}
              output={directions.output}
              selectedDirectionId={
                pendingSelection?.stage === "DIRECTIONS"
                  ? pendingSelection.item_id
                  : directions.selected_item_id
              }
              versionId={directions.version_id}
            />
          ) : (
            <div className={styles.empty}>暂无 Directions 结果</div>
          )}
        </section>

        <section className={styles.panel}>
          <PanelHeader title="Logo" versionId={logo?.version_id} />
          {logo ? (
            <LogoResult
              assetUrls={assetUrls}
              onSelect={handleSelect}
              output={logo.output}
              selectedLogoId={
                pendingSelection?.stage === "LOGO"
                  ? pendingSelection.item_id
                  : logo.selected_item_id
              }
              versionId={logo.version_id}
            />
          ) : (
            <div className={styles.empty}>暂无 Logo 结果</div>
          )}
        </section>
      </div>
    </section>
  );
}

function PanelHeader({ title, versionId }: { title: string; versionId?: string }) {
  return (
    <div className={styles.header}>
      <h2>{title}</h2>
      <span>{versionId ?? "N/A"}</span>
    </div>
  );
}
