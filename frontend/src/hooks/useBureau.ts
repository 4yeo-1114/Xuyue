import { useState, useEffect, useCallback } from "react";
import type { WarningAlert, TaskTicket, TicketStatus } from "@/types/bureau";
import {
  getWarnings,
  getTickets,
  createTicket as createTicketApi,
  updateTicketStatus,
} from "@/services/bureau";

export function useWarnings() {
  const [warnings, setWarnings] = useState<WarningAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const data = getWarnings();
      setWarnings(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "获取预警数据失败");
    } finally {
      setLoading(false);
    }
  }, []);

  return { warnings, loading, error };
}

export function useTickets() {
  const [tickets, setTickets] = useState<TaskTicket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    try {
      const data = getTickets();
      setTickets(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "获取督办数据失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const createTicket = useCallback(
    (ticket: Omit<TaskTicket, "id" | "createdAt">) => {
      const created = createTicketApi(ticket);
      setTickets((prev) => [created, ...prev]);
      return created;
    },
    [],
  );

  const updateStatus = useCallback((id: string, status: TicketStatus) => {
    updateTicketStatus(id, status);
    setTickets((prev) => prev.map((t) => (t.id === id ? { ...t, status } : t)));
  }, []);

  return { tickets, loading, error, createTicket, updateStatus };
}
