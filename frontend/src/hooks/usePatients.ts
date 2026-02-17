import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";

export function usePatients() {
  return useQuery({
    queryKey: ["patients"],
    queryFn: api.getPatients,
  });
}

export function usePatient(id: number | undefined) {
  return useQuery({
    queryKey: ["patients", id],
    queryFn: () => api.getPatient(id!),
    enabled: id !== undefined,
  });
}
