import type { ReactNode } from "react";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

interface MainAreaProps {
  sidebar: ReactNode;
  children: ReactNode;
}

export function MainArea({ sidebar, children }: MainAreaProps) {
  return (
    <div className="min-h-screen">
      <Header />
      <Sidebar>{sidebar}</Sidebar>
      <main className="ml-[260px] mt-14 h-[calc(100vh-3.5rem)]">{children}</main>
    </div>
  );
}
