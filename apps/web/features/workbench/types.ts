export type WorkbenchStage =
  | "DIRECTIONS"
  | "LOGO"
  | "IP";

export type WorkbenchStageStatus =
  | "LOCKED"
  | "GENERATING"
  | "AWAITING_DECISION"
  | "CONFIRMED"
  | "STALE";

export type VersionItemSelection = {
  stage: WorkbenchStage;
  version_id: string;
  item_id: string;
};

export type WorkbenchStageSummary = {
  stage: WorkbenchStage;
  status: WorkbenchStageStatus;
  version_id: string | null;
  selected_item_id: string | null;
};

export type PaletteColor = {
  name: string;
  hex: string;
  usage: string;
};
