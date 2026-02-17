import { useMutation } from "@tanstack/react-query";
import { api } from "@/services/api";

export function useBriefing() {
  return useMutation({
    mutationFn: (patientId: number) => api.generateBriefing(patientId),
  });
}
