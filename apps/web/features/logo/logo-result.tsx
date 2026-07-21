import Image from "next/image";

import type { VersionItemSelection } from "@/features/workbench/types";

import type { LogoConcept, LogoOutput } from "./types";
import styles from "./logo-result.module.css";

type LogoResultProps = {
  assetUrls?: Record<string, string>;
  isDisabled?: boolean;
  output: LogoOutput;
  selectedLogoId?: string | null;
  versionId: string;
  onSelect: (selection: VersionItemSelection) => void;
};

export function LogoResult({
  assetUrls = {},
  isDisabled = false,
  output,
  selectedLogoId,
  versionId,
  onSelect,
}: LogoResultProps) {
  return (
    <section className={styles.section}>
      <div className={styles.grid}>
        {output.concepts.map((concept) => (
          <LogoCard
            assetUrl={assetUrls[concept.preview_asset_id]}
            concept={concept}
            isDisabled={isDisabled}
            isSelected={selectedLogoId === concept.id}
            key={concept.id}
            onSelect={() =>
              onSelect({
                stage: "LOGO",
                version_id: versionId,
                item_id: concept.id,
              })
            }
          />
        ))}
      </div>
    </section>
  );
}

function LogoCard({
  assetUrl,
  concept,
  isDisabled,
  isSelected,
  onSelect,
}: {
  assetUrl?: string;
  concept: LogoConcept;
  isDisabled: boolean;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <article className={`${styles.card} ${isSelected ? styles.selected : ""}`}>
      <div className={styles.preview}>
        {assetUrl ? (
          <Image alt={concept.name} fill sizes="(max-width: 1100px) 100vw, 33vw" src={assetUrl} unoptimized />
        ) : (
          <span className={styles.assetFallback}>{concept.preview_asset_id}</span>
        )}
      </div>

      <div className={styles.body}>
        <div className={styles.title}>
          <h3>{concept.name}</h3>
          <small>{concept.id}</small>
        </div>
        <MetaBlock label="设计理由" value={concept.rationale} />
        <MetaBlock label="符号含义" value={concept.symbolism} />
        <MetaBlock label="造型语言" value={concept.shape_language} />
        <MetaBlock label="色彩策略" value={concept.color_strategy} />
      </div>

      <div className={styles.actions}>
        <button
          className={styles.button}
          disabled={isDisabled || isSelected}
          onClick={onSelect}
          type="button"
        >
          {isSelected ? "已选择" : "选择 Logo"}
        </button>
      </div>
    </article>
  );
}

function MetaBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metaBlock}>
      <span>{label}</span>
      <p>{value}</p>
    </div>
  );
}
