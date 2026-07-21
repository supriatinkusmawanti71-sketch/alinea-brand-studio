import { EmptyState } from "@/components/ui";
import type { ProjectResponse } from "@/lib/api/types";

type ProjectListProps = {
  onSelect: (projectId: string) => void;
  projects: ProjectResponse[];
  selectedProjectId: string | null;
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function ProjectList({ onSelect, projects, selectedProjectId }: ProjectListProps) {
  if (projects.length === 0) {
    return <EmptyState title="还没有项目">点击“新建项目”开始第一条品牌生成流程。</EmptyState>;
  }

  return (
    <div className="project-list">
      {projects.map((project) => (
        <button
          className={`project-list-item ${
            selectedProjectId === project.id ? "project-list-item--active" : ""
          }`}
          key={project.id}
          onClick={() => onSelect(project.id)}
          type="button"
        >
          <span>
            <strong>{project.name}</strong>
            <small>{formatDate(project.updated_at)}</small>
          </span>
          <em>{project.current_stage}</em>
        </button>
      ))}
    </div>
  );
}

