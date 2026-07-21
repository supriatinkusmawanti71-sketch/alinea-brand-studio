import type { VersionItemSelection } from "@/features/workbench/types";

import type { DirectionItem, DirectionOutput } from "./types";
import styles from "./directions-result.module.css";

type DirectionsResultProps = {
  isDisabled?: boolean;
  output: DirectionOutput;
  versionId: string;
  selectedDirectionId?: string | null;
  onSelect: (selection: VersionItemSelection) => void;
};

export function DirectionsResult({
  isDisabled = false,
  output,
  selectedDirectionId,
  versionId,
  onSelect,
}: DirectionsResultProps) {
  return (
    <section className={styles.section}>
      <div className={styles.brief}>
        <BriefItem label="定位" value={output.brief.positioning} />
        <BriefItem label="受众洞察" value={output.brief.audience_insight} />
        <BriefItem label="品牌承诺" value={output.brief.brand_promise} />
        <BriefItem label="语气" value={output.brief.tone} />
      </div>

      <div className={styles.grid}>
        {output.directions.map((direction) => (
          <DirectionCard
            direction={direction}
            isDisabled={isDisabled}
            isSelected={selectedDirectionId === direction.id}
            key={direction.id}
            onSelect={() =>
              onSelect({
                stage: "DIRECTIONS",
                version_id: versionId,
                item_id: direction.id,
              })
            }
          />
        ))}
      </div>
    </section>
  );
}

function BriefItem({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.briefItem}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DirectionCard({
  direction,
  isDisabled,
  isSelected,
  onSelect,
}: {
  direction: DirectionItem;
  isDisabled: boolean;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <article className={`${styles.card} ${isSelected ? styles.selected : ""}`}>
      <div className={styles.header}>
        <div className={styles.title}>
          <h3>{direction.name}</h3>
          <small>{direction.id}</small>
        </div>
      </div>

      <p className={styles.copy}>{direction.concept}</p>

      <div className={styles.keywords}>
        {direction.keywords.map((keyword) => (
          <span className={styles.keyword} key={keyword}>
            {keyword}
          </span>
        ))}
      </div>

      <div className={styles.palette}>
        {direction.palette.map((color) => (
          <span className={styles.color} key={`${direction.id}-${color.hex}`}>
            <span className={styles.swatch} style={{ backgroundColor: color.hex }} />
            <span>{color.name}</span>
          </span>
        ))}
      </div>

      <div className={styles.meta}>
        <MetaBlock label="标题字体" value={direction.typography.heading_style} />
        <MetaBlock label="正文字体" value={direction.typography.body_style} />
        <MetaBlock label="构图" value={direction.composition} />
        <MetaBlock label="理由" value={direction.rationale} />
      </div>

      <div className={styles.actions}>
        <button
          className={styles.button}
          disabled={isDisabled || isSelected}
          onClick={onSelect}
          type="button"
        >
          {isSelected ? "已选择" : "选择方向"}
        </button>
      </div>
    </article>
  );
}

function MetaBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metaBlock}>
      <span className={styles.metaLabel}>{label}</span>
      <p>{value}</p>
    </div>
  );
}
