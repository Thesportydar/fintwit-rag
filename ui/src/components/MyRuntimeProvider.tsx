"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  AssistantRuntimeProvider,
  type ThreadHistoryAdapter,
  type ThreadMessage,
} from "@assistant-ui/react";
import { HttpAgent } from "@ag-ui/client";
import { useAgUiRuntime } from "@assistant-ui/react-ag-ui";
import { getCognitoAccessToken } from "../lib/cognito";

const STORAGE_KEY = "fintwit_agui_threads";

export interface ThreadItem {
  id: string;
  title: string;
  updatedAt: string;
}

export interface MyThreadsContextType {
  threads: ThreadItem[];
  currentThreadId: string;
  onSelectThread: (id: string) => void;
  onNewThread: () => void;
  onDeleteThread: (id: string) => void;
  onAppendMessage: (text: string) => void;
}

export const MyThreadsContext = createContext<MyThreadsContextType | null>(null);

export function useMyThreads() {
  const ctx = useContext(MyThreadsContext);
  if (!ctx) throw new Error("useMyThreads must be used within MyRuntimeProvider");
  return ctx;
}

function loadSavedThreads(): Record<string, { id: string; messages: ThreadMessage[] }> {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (err) {
    console.warn("Failed to load threads from localStorage", err);
  }
  return {};
}

function computeThreadList(
  threadsMap: Record<string, { id: string; messages: ThreadMessage[] }>,
): ThreadItem[] {
  return Object.values(threadsMap)
    .map((t) => {
      let title = "Nuevo chat";
      const firstUserMsg = t.messages?.find((m) => m.role === "user");
      if (firstUserMsg && firstUserMsg.content?.length > 0) {
        const textPart = firstUserMsg.content.find((p: any) => p.type === "text");
        if (textPart && "text" in textPart && textPart.text) {
          title =
            textPart.text.slice(0, 30) + (textPart.text.length > 30 ? "..." : "");
        }
      }
      return {
        id: t.id,
        title,
        updatedAt: new Date().toISOString(),
      };
    })
    .reverse();
}

export function MyRuntimeProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCognitoAccessToken()
      .then(setToken)
      .catch((err) => {
        console.error("Cognito Auth Error:", err);
        setError(err instanceof Error ? err.message : String(err));
      });
  }, []);

  if (error) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-2 p-6 text-center text-red-500">
        <p className="font-semibold">Error de autenticación con Amazon Cognito</p>
        <p className="text-sm text-zinc-400">{error}</p>
        <button
          onClick={() => {
            sessionStorage.removeItem("fintwit_access_token");
            window.location.reload();
          }}
          className="mt-4 rounded-md bg-zinc-800 px-4 py-2 text-sm text-white hover:bg-zinc-700"
        >
          Reintentar
        </button>
      </div>
    );
  }

  if (!token) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 bg-zinc-950 text-zinc-400">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-500 border-t-transparent" />
        <p className="text-sm">Iniciando sesión segura en FinTwit...</p>
      </div>
    );
  }

  return <AuthenticatedRuntimeProvider token={token}>{children}</AuthenticatedRuntimeProvider>;
}

function AuthenticatedRuntimeProvider({
  token,
  children,
}: {
  token: string;
  children: ReactNode;
}) {
  const [threadsList, setThreadsList] = useState<ThreadItem[]>(() => {
    const initialMap = loadSavedThreads();
    return computeThreadList(initialMap);
  });

  const [currentThreadId, setCurrentThreadId] = useState<string>(() => {
    const params = new URLSearchParams(window.location.search);
    const urlThreadId = params.get("thread");
    const initialMap = loadSavedThreads();
    if (urlThreadId && initialMap[urlThreadId]) {
      return urlThreadId;
    }
    const ids = Object.keys(initialMap);
    if (ids.length > 0) {
      return ids[ids.length - 1];
    }
    const newId = crypto.randomUUID();
    return newId;
  });

  // URL Sync
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("thread") !== currentThreadId) {
      params.set("thread", currentThreadId);
      window.history.replaceState(null, "", `?${params.toString()}`);
    }
  }, [currentThreadId]);

  const handleThreadTitleUpdate = useCallback((threadId: string, title: string) => {
    setThreadsList((prev) => {
      const current = prev.find((t) => t.id === threadId);
      if (current && current.title === title) return prev;
      if (!current) {
        return [{ id: threadId, title, updatedAt: new Date().toISOString() }, ...prev];
      }
      return prev.map((t) => (t.id === threadId ? { ...t, title } : t));
    });
  }, []);

  const handleNewThread = useCallback(() => {
    const newId = crypto.randomUUID();
    setThreadsList((prev) => [
      { id: newId, title: "Nuevo chat", updatedAt: new Date().toISOString() },
      ...prev,
    ]);
    setCurrentThreadId(newId);
  }, []);

  const handleDeleteThread = useCallback(
    (id: string) => {
      const saved = loadSavedThreads();
      delete saved[id];
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
      } catch (e) {
        console.warn("Failed to delete thread from localStorage", e);
      }

      setThreadsList((prev) => prev.filter((t) => t.id !== id));

      if (currentThreadId === id) {
        const remainingIds = Object.keys(saved);
        if (remainingIds.length > 0) {
          setCurrentThreadId(remainingIds[remainingIds.length - 1]);
        } else {
          const freshId = crypto.randomUUID();
          setCurrentThreadId(freshId);
        }
      }
    },
    [currentThreadId],
  );

  const appendMessageRef = useRef<((text: string) => void) | null>(null);

  const contextValue = useMemo<MyThreadsContextType>(
    () => ({
      threads: threadsList,
      currentThreadId,
      onSelectThread: (id) => {
        if (id !== currentThreadId) {
          setCurrentThreadId(id);
        }
      },
      onNewThread: handleNewThread,
      onDeleteThread: handleDeleteThread,
      onAppendMessage: (text) => {
        appendMessageRef.current?.(text);
      },
    }),
    [threadsList, currentThreadId, handleNewThread, handleDeleteThread],
  );

  return (
    <MyThreadsContext.Provider value={contextValue}>
      <SingleThreadRuntime
        key={currentThreadId}
        token={token}
        threadId={currentThreadId}
        onThreadTitleUpdate={handleThreadTitleUpdate}
        appendMessageRef={appendMessageRef}
      >
        {children}
      </SingleThreadRuntime>
    </MyThreadsContext.Provider>
  );
}

function SingleThreadRuntime({
  token,
  threadId,
  onThreadTitleUpdate,
  appendMessageRef,
  children,
}: {
  token: string;
  threadId: string;
  onThreadTitleUpdate: (threadId: string, title: string) => void;
  appendMessageRef: React.MutableRefObject<((text: string) => void) | null>;
  children: ReactNode;
}) {
  const agentUrl = import.meta.env.VITE_AGENTCORE_RUNTIME_URL;
  if (!agentUrl) {
    throw new Error("Falta VITE_AGENTCORE_RUNTIME_URL en variables de entorno");
  }

  const agent = useMemo(() => {
    return new HttpAgent({
      url: agentUrl,
      threadId,
      headers: {
        Authorization: `Bearer ${token}`,
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": threadId,
      },
      fetch: async (input, init) => {
        const freshToken = await getCognitoAccessToken();
        const headers = new Headers(init?.headers);
        headers.set("Authorization", `Bearer ${freshToken}`);
        headers.set("X-Amzn-Bedrock-AgentCore-Runtime-Session-Id", threadId);

        let res = await fetch(input, { ...init, headers });
        if (res.status === 401) {
          console.warn("Got 401 from Bedrock AgentCore, forcing token refresh and retrying...");
          const renewedToken = await getCognitoAccessToken(undefined, undefined, true);
          headers.set("Authorization", `Bearer ${renewedToken}`);
          res = await fetch(input, { ...init, headers });
        }
        return res;
      },
    });
  }, [agentUrl, token, threadId]);

  const historyAdapter = useMemo<ThreadHistoryAdapter>(
    () => ({
      load: async () => {
        const savedMap = loadSavedThreads();
        const threadData = savedMap[threadId];
        if (!threadData || !threadData.messages || threadData.messages.length === 0) {
          return { messages: [], headId: null };
        }
        let parentId: string | null = null;
        const messages = threadData.messages.map((m) => {
          const entry = { parentId, message: m };
          parentId = m.id;
          return entry;
        });
        return {
          messages,
          headId: parentId,
        };
      },
      append: async ({ message }) => {
        const savedMap = loadSavedThreads();
        const threadData = savedMap[threadId] || { id: threadId, messages: [] };
        const existingIdx = threadData.messages.findIndex((m) => m.id === message.id);
        if (existingIdx >= 0) {
          threadData.messages[existingIdx] = message;
        } else {
          threadData.messages.push(message);
        }
        savedMap[threadId] = threadData;
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(savedMap));
        } catch (e) {
          console.warn("Failed to persist thread append", e);
        }

        if (message.role === "user" && message.content?.length > 0) {
          const textPart = message.content.find((p: any) => p.type === "text");
          if (textPart && "text" in textPart && textPart.text) {
            const title =
              textPart.text.slice(0, 30) + (textPart.text.length > 30 ? "..." : "");
            onThreadTitleUpdate(threadId, title);
          }
        }
      },
      update: async ({ message }) => {
        const savedMap = loadSavedThreads();
        const threadData = savedMap[threadId] || { id: threadId, messages: [] };
        const existingIdx = threadData.messages.findIndex((m) => m.id === message.id);
        if (existingIdx >= 0) {
          threadData.messages[existingIdx] = message;
        } else {
          threadData.messages.push(message);
        }
        savedMap[threadId] = threadData;
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(savedMap));
        } catch (e) {
          console.warn("Failed to persist thread update", e);
        }
      },
    }),
    [threadId, onThreadTitleUpdate],
  );

  const adapters = useMemo(
    () => ({
      history: historyAdapter,
    }),
    [historyAdapter],
  );

  const runtime = useAgUiRuntime({
    agent,
    adapters,
  });

  useEffect(() => {
    appendMessageRef.current = (text: string) => {
      runtime.thread.append({
        role: "user",
        content: [{ type: "text", text }],
      });
    };
    return () => {
      appendMessageRef.current = null;
    };
  }, [runtime, appendMessageRef]);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
