import { useMutation } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { BriefingRuntime } from "@/types";

export function useBriefing() {
  return useMutation({
    mutationFn: ({
      patientId,
      runtime,
    }: {
      patientId: number;
      runtime: BriefingRuntime;
    }) => api.generateBriefing(patientId, runtime),
  });
}
