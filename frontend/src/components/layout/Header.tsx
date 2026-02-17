import { Stethoscope } from "lucide-react";

export function Header() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 flex h-14 items-center gap-2 border-b border-border/50 bg-background/95 px-4 backdrop-blur-sm">
      <Stethoscope className="size-5 text-primary" />
      <h1 className="text-lg font-semibold tracking-tight">Build AI Agents</h1>
    </header>
  );
}
