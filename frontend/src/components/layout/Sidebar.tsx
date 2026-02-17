import type { ReactNode } from "react";

interface SidebarProps {
  children: ReactNode;
}

export function Sidebar({ children }: SidebarProps) {
  return (
    <aside className="fixed left-0 top-14 bottom-0 w-[260px] overflow-y-auto border-r border-sidebar-border bg-sidebar">
      {children}
    </aside>
  );
}
