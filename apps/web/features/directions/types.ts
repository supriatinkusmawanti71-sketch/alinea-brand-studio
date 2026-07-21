import type { PaletteColor } from "@/features/workbench/types";

export type DirectionBrief = {
  positioning: string;
  audience_insight: string;
  brand_promise: string;
  tone: string;
};

export type TypographyDirection = {
  heading_style: string;
  body_style: string;
};

export type DirectionItem = {
  id: string;
  name: string;
  concept: string;
  keywords: string[];
  palette: PaletteColor[];
  typography: TypographyDirection;
  composition: string;
  rationale: string;
  risks: string[];
  image_prompt: string;
  preview_asset_id: string;
};

export type DirectionOutput = {
  schema_version: number;
  brief: DirectionBrief;
  directions: DirectionItem[];
};

export type DirectionSelectionRequest = {
  version_id: string;
  direction_id: string;
};

export function buildDirectionSelectionRequest(
  versionId: string,
  directionId: string,
): DirectionSelectionRequest {
  return {
    version_id: versionId,
    direction_id: directionId,
  };
}
