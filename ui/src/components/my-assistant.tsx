"use client";

import { useState, useEffect, useCallback } from "react";
import {
  AssistantRuntimeProvider,
  type AppendMessage,
  type ThreadMessageLike,
  useExternalStoreRuntime,
} from "@assistant-ui/react";
import { Claude } from "./claude";

const generateUUID = () => {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
};

export interface ThreadItem {
  id: string;
  title: string;
  updatedAt: string;
}

export interface FilterSettings {
  startDate: string;
  endDate: string;
  userHandles: string;
}

const API_URL = import.meta.env.VITE_API_URL as string;

export function MyAssistant() {
  // Active Thread ID State
  const [threadId, setThreadId] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    try {
      const params = new URLSearchParams(window.location.search);
      const queryId = params.get("threadId");
      if (queryId) return queryId;

      const savedActive = localStorage.getItem("fintwit_rag_active_thread_id");
      if (savedActive) return savedActive;
    } catch (e) {
      console.error("Error reading active thread ID from localStorage:", e);
    }

    const newId = generateUUID();
    try {
      localStorage.setItem("fintwit_rag_active_thread_id", newId);
    } catch (e) {
      console.error("Error writing active thread ID to localStorage:", e);
    }
    return newId;
  });

  // Threads List State
  const [threads, setThreads] = useState<ThreadItem[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const saved = localStorage.getItem("fintwit_rag_threads");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) return parsed;
      }
    } catch (e) {
      console.error("Error loading threads from localStorage:", e);
    }
    return [];
  });

  // Messages State
  const [messages, setMessages] = useState<readonly ThreadMessageLike[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const params = new URLSearchParams(window.location.search);
      const queryId = params.get("threadId");
      const activeId = queryId || localStorage.getItem("fintwit_rag_active_thread_id");
      if (!activeId) return [];

      const savedMessages = localStorage.getItem(`fintwit_rag_messages_${activeId}`);
      if (savedMessages) {
        const parsed = JSON.parse(savedMessages);
        if (Array.isArray(parsed)) return parsed;
      }
    } catch (e) {
      console.error("Error loading messages from localStorage:", e);
    }
    return [];
  });

  // Filter Settings State
  const [filters, setFilters] = useState<FilterSettings>({
    startDate: "",
    endDate: "",
    userHandles: "",
  });

  // Loading & Error States
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Sync active thread ID to URL query param
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const url = new URL(window.location.href);
      if (threadId) {
        url.searchParams.set("threadId", threadId);
        localStorage.setItem("fintwit_rag_active_thread_id", threadId);
      } else {
        url.searchParams.delete("threadId");
      }
      window.history.replaceState({}, "", url.toString());
    } catch (e) {
      console.error("Error syncing threadId to URL/localStorage:", e);
    }
  }, [threadId]);

  // Sync threads list to localStorage
  useEffect(() => {
    try {
      localStorage.setItem("fintwit_rag_threads", JSON.stringify(threads));
    } catch (e) {
      console.error("Error saving threads list to localStorage:", e);
    }
  }, [threads]);

  // Ensure thread is in list
  const ensureThreadInList = useCallback((id: string, firstQuery: string) => {
    setThreads((prev) => {
      const exists = prev.some((t) => t.id === id);
      if (exists) return prev;

      const newThread: ThreadItem = {
        id,
        title: firstQuery.length > 40 ? firstQuery.substring(0, 37) + "..." : firstQuery,
        updatedAt: new Date().toISOString(),
      };

      return [newThread, ...prev];
    });
  }, []);

  // Delete Thread
  const handleDeleteThread = useCallback((idToDelete: string) => {
    setThreads((prev) => prev.filter((t) => t.id !== idToDelete));
    try {
      localStorage.removeItem(`fintwit_rag_messages_${idToDelete}`);
    } catch (e) {
      console.error("Error removing messages from localStorage for thread:", idToDelete, e);
    }

    if (threadId === idToDelete) {
      const nextId = generateUUID();
      setThreadId(nextId);
      setMessages([]);
    }
  }, [threadId]);

  // Select Thread
  const handleSelectThread = useCallback((id: string) => {
    setThreadId(id);
    try {
      const savedMessages = localStorage.getItem(`fintwit_rag_messages_${id}`);
      if (savedMessages) {
        const parsed = JSON.parse(savedMessages);
        if (Array.isArray(parsed)) {
          setMessages(parsed);
          setError(null);
          return;
        }
      }
    } catch (e) {
      console.error("Error loading messages on select thread:", id, e);
    }
    setMessages([]);
    setError(null);
  }, []);

  // Create New Thread
  const handleNewThread = useCallback(() => {
    const nextId = generateUUID();
    setThreadId(nextId);
    setMessages([]);
    setError(null);
  }, []);

  // Send message API request
  const onNew = useCallback(
    async (message: AppendMessage) => {
      const promptText = message.content
        .filter((part) => part.type === "text")
        .map((part) => part.text)
        .join(" ");

      if (!promptText.trim()) return;

      // Ensure thread list has this thread
      ensureThreadInList(threadId, promptText);

      // Inject filter parameters into the query string
      let injectedPrompt = promptText;
      const filterParts: string[] = [];
      if (filters.startDate) filterParts.push(`desde ${filters.startDate}`);
      if (filters.endDate) filterParts.push(`hasta ${filters.endDate}`);
      if (filters.userHandles) {
        const cleanedHandles = filters.userHandles
          .split(",")
          .map((h) => h.trim().replace(/^@/, ""))
          .filter(Boolean)
          .join(", ");
        if (cleanedHandles) {
          filterParts.push(`usuarios: ${cleanedHandles}`);
        }
      }

      if (filterParts.length > 0) {
        injectedPrompt = `${promptText} [Filtros seleccionados: ${filterParts.join(", ")}]`;
      }

      // Add user message to local state immediately
      const newUserMsg: ThreadMessageLike = {
        id: `user-${Date.now()}`,
        role: "user",
        content: [{ type: "text", text: promptText }],
      };

      const updatedMessages = [...messages, newUserMsg];
      setMessages(updatedMessages);
      try {
        localStorage.setItem(`fintwit_rag_messages_${threadId}`, JSON.stringify(updatedMessages));
      } catch (e) {
        console.error("Error saving messages to localStorage:", e);
      }

      setIsLoading(true);
      setError(null);

      try {
        const apiMessage = {
          role: "user",
          content: injectedPrompt,
        };

        const response = await fetch(API_URL, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            thread_id: threadId,
            messages: [apiMessage],
          }),
        });

        if (!response.ok) {
          throw new Error(`Error de red: ${response.status} ${response.statusText}`);
        }

        const data = await response.json();

        // El frontend es la fuente de verdad. Extraemos solo el último mensaje (la respuesta del Assistant)
        // del array que devuelve la API y lo concatenamos al historial local.
        if (data.messages && Array.isArray(data.messages) && data.messages.length > 0) {
          const lastApiMsg = data.messages[data.messages.length - 1];
          const textContent = typeof lastApiMsg.content === "string"
            ? lastApiMsg.content
            : JSON.stringify(lastApiMsg.content);

          const newAssistantMsg: ThreadMessageLike = {
            id: `assistant-${Date.now()}`,
            role: "assistant",
            content: [{ type: "text", text: textContent }],
          };

          const finalMessages = [...updatedMessages, newAssistantMsg];
          setMessages(finalMessages);

          try {
            localStorage.setItem(`fintwit_rag_messages_${threadId}`, JSON.stringify(finalMessages));
          } catch (e) {
            console.error("Error saving final messages to localStorage:", e);
          }
        } else {
          throw new Error("Formato de respuesta incorrecto o sin mensajes.");
        }
      } catch (err: any) {
        console.error("API call failed:", err);
        const errorMessage = err.message || "Error al conectar con la API.";
        setError(new Error(errorMessage));

        // Append offline warning message to local history
        const assistantErrorMsg: ThreadMessageLike = {
          id: `assistant-error-${Date.now()}`,
          role: "assistant",
          content: [
            {
              type: "text",
              text: `⚠️ **Error de Conexión:** No se pudo obtener respuesta del RAG Agent. La API (${API_URL}) está fuera de línea en este momento. \n\n*Detalle del error: ${errorMessage}*`,
            },
          ],
        };

        const errorList = [...updatedMessages, assistantErrorMsg];
        setMessages(errorList);
        try {
          localStorage.setItem(`fintwit_rag_messages_${threadId}`, JSON.stringify(errorList));
        } catch (e) {
          console.error("Error saving error messages list to localStorage:", e);
        }
      } finally {
        setIsLoading(false);
      }
    },
    [threadId, messages, filters, ensureThreadInList]
  );

  const submitPrompt = useCallback(
    async (prompt: string) => {
      const appendMsg = {
        parentId: messages[messages.length - 1]?.id ?? null,
        role: "user",
        content: [{ type: "text", text: prompt }],
      } as any;
      await onNew(appendMsg);
    },
    [messages, onNew]
  );

  const runtime = useExternalStoreRuntime({
    isRunning: isLoading,
    messages,
    convertMessage: (message) => message,
    setMessages: (newMsgs) => {
      setMessages(newMsgs);
      try {
        localStorage.setItem(`fintwit_rag_messages_${threadId}`, JSON.stringify(newMsgs));
      } catch (e) {
        console.error("Error writing messages in setMessages runtime callback:", e);
      }
    },
    onNew,
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <Claude
        error={error}
        isLoading={isLoading}
        threadId={threadId}
        threads={threads}
        onSelectThread={handleSelectThread}
        onNewThread={handleNewThread}
        onDeleteThread={handleDeleteThread}
        filters={filters}
        setFilters={setFilters}
        onCancel={() => setIsLoading(false)}
        onSuggestionClick={submitPrompt}
      />
    </AssistantRuntimeProvider>
  );
}
