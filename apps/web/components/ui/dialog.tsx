import type { ReactNode } from "react";

import { Button } from "./button";

type DialogProps = {
  children: ReactNode;
  isOpen: boolean;
  onClose: () => void;
  title: string;
};

export function Dialog({ children, isOpen, onClose, title }: DialogProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <div aria-modal="true" className="dialog-backdrop" role="dialog">
      <section className="dialog-panel">
        <header className="dialog-header">
          <h2>{title}</h2>
          <Button aria-label="关闭弹窗" onClick={onClose} variant="ghost">
            关闭
          </Button>
        </header>
        {children}
      </section>
    </div>
  );
}

