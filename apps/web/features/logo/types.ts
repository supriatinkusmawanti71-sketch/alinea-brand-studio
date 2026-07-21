export type LogoConcept = {
  id: string;
  name: string;
  rationale: string;
  symbolism: string;
  shape_language: string;
  color_strategy: string;
  image_prompt: string;
  preview_asset_id: string;
};

export type LogoOutput = {
  schema_version: number;
  concepts: LogoConcept[];
};

export type LogoSelectionRequest = {
  version_id: string;
  logo_id: string;
};

export function buildLogoSelectionRequest(versionId: string, logoId: string): LogoSelectionRequest {
  return {
    version_id: versionId,
    logo_id: logoId,
  };
}
