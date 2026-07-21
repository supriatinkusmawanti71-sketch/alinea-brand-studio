import type { ReactNode } from "react";

import { Button } from "./button";

type FeedbackProps = {
  children?: ReactNode;
  title: string;
};

export function LoadingState({ title }: Pick<FeedbackProps, "title">) {
  return (
    <div className="feedback feedback--loading" role="status">
      <span aria-hidden="true" className="spinner" />
      <strong>{title}</strong>
    </div>
  );
}

export function ErrorState({
  actionLabel,
  children,
  onAction,
  title,
}: FeedbackProps & { actionLabel?: string; onAction?: () => void }) {
  return (
    <div className="feedback feedback--error" role="alert">
      <strong>{title}</strong>
      {children ? <p>{children}</p> : null}
      {actionLabel && onAction ? (
        <Button onClick={onAction} variant="secondary">
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({ children, title }: FeedbackProps) {
  return (
    <div className="feedback feedback--empty">
      <strong>{title}</strong>
      {children ? <p>{children}</p> : null}
    </div>
  );
}

