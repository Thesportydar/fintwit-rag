"use client";

import { useCallback, useEffect, useMemo, useState, type FC } from "react";
import {
  ActionBarPrimitive,
  AuiIf,
  AttachmentPrimitive,
  ChainOfThoughtPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  type ReasoningMessagePartComponent,
  type ToolCallMessagePartComponent,
  useAui,
  useAuiState,
} from "@assistant-ui/react";
import {
  ArrowUpIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClipboardIcon,
  Cross2Icon,
  MixerHorizontalIcon,
  PlusIcon,
  StopIcon,
} from "@radix-ui/react-icons";
import {
  AlertCircle,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  MessageSquare,
  Calendar,
  User,
  Menu,
  X,
  SlidersHorizontal,
} from "lucide-react";
import { useShallow } from "zustand/react/shallow";
import { MarkdownText } from "./markdown-text";
import type { ThreadItem, FilterSettings } from "./my-assistant";

const SUGGESTIONS = [
  "¿Qué opina @elonmusk sobre el precio de Tesla y Bitcoin?",
  "Buscame tweets sobre inflación y tasas de la FED en Noviembre 2023",
  "¿Qué se comenta en Fintwit sobre regulaciones cripto recientemente?",
];

export function Claude({
  error,
  isLoading,
  threadId,
  threads,
  onSelectThread,
  onNewThread,
  onDeleteThread,
  filters,
  setFilters,
  onCancel,
  onSuggestionClick,
}: {
  error: Error | null;
  isLoading: boolean;
  threadId: string;
  threads: ThreadItem[];
  onSelectThread: (id: string) => void;
  onNewThread: () => void;
  onDeleteThread: (id: string) => void;
  filters: FilterSettings;
  setFilters: React.Dispatch<React.SetStateAction<FilterSettings>>;
  onCancel: () => void;
  onSuggestionClick: (prompt: string) => void;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);

  // Check if any filter is active
  const hasActiveFilters = useMemo(() => {
    return !!(filters.startDate || filters.endDate || filters.userHandles);
  }, [filters]);

  const handleClearFilters = () => {
    setFilters({ startDate: "", endDate: "", userHandles: "" });
  };

  return (
    <div className="flex h-dvh overflow-hidden bg-[#2b2a27] font-sans text-[#eee]">
      {/* Sidebar - Persistent History & Filters */}
      <div
        className={`transition-all duration-300 ease-in-out ${
          sidebarOpen ? "w-80" : "w-0"
        } flex flex-col border-r border-[#6c6a6040] bg-[#1f1e1b] overflow-hidden shrink-0`}
      >
        {/* Sidebar Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#6c6a6020]">
          <div className="flex items-center gap-2">
            <div>
              <h2 className="text-sm font-bold tracking-wider text-[#f1efe8]">FINTWIT RAG</h2>
              <p className="text-[10px] text-[#9a9893] uppercase tracking-wider">Twitter Search Bot</p>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="p-1 rounded hover:bg-[#2b2a27] text-[#9a9893] hover:text-[#eee] transition"
            title="Cerrar barra lateral"
          >
            <X size={16} />
          </button>
        </div>

        {/* Action Button */}
        <div className="p-4">
          <button
            onClick={onNewThread}
            className="w-full rounded-xl border border-[#ae5630]/30 hover:border-[#ae5630] bg-[#ae5630]/10 hover:bg-[#ae5630]/20 text-[#eee] font-medium py-2.5 px-4 transition duration-300 flex items-center justify-center gap-2 shadow-sm text-sm"
          >
            <PlusIcon height={16} width={16} />
            Nueva Conversación
          </button>
        </div>

        {/* Thread History list */}
        <div className="flex-1 overflow-y-auto px-4 py-2 space-y-1">
          <div className="text-[10px] text-[#9a9893] uppercase font-bold tracking-widest pl-2 mb-2">
            Historial de chats
          </div>
          {threads.length === 0 ? (
            <div className="text-xs text-[#6b6a68] italic pl-2 py-4">
              No hay conversaciones guardadas
            </div>
          ) : (
            threads.map((t) => {
              const isActive = t.id === threadId;
              return (
                <div
                  key={t.id}
                  onClick={() => onSelectThread(t.id)}
                  className={`group flex items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-xs transition cursor-pointer ${
                    isActive
                      ? "bg-[#393937] text-white border-l-2 border-[#ae5630]"
                      : "text-[#b8b5a9] hover:bg-[#2b2a27] hover:text-[#eee]"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate min-w-0">
                    <MessageSquare size={13} className="shrink-0 opacity-70" />
                    <span className="truncate font-medium">{t.title}</span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteThread(t.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-[#393937] text-[#9a9893] hover:text-[#d97c66] transition shrink-0"
                    title="Eliminar chat"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Search Filters Section */}
        <div className="border-t border-[#6c6a6040] bg-[#1a1a18]/60 p-4 space-y-3">
          <button 
            onClick={() => setFiltersOpen(!filtersOpen)}
            className="w-full flex items-center justify-between text-xs uppercase font-bold tracking-widest text-[#9a9893] hover:text-[#eee] transition"
          >
            <div className="flex items-center gap-2">
              <SlidersHorizontal size={12} />
              Filtros del LLM
            </div>
            {filtersOpen ? <ChevronDownIcon /> : <ChevronRightIcon />}
          </button>
          
          {filtersOpen && (
            <div className="space-y-3 pt-2">
              <div className="space-y-2.5">
                <div>
                  <label className="flex items-center gap-1 text-[10px] text-[#9a9893] mb-1 font-medium">
                    <Calendar size={10} />
                    Desde (Fecha de Inicio)
                  </label>
                  <input
                    type="date"
                    value={filters.startDate}
                    onChange={(e) => setFilters((prev) => ({ ...prev, startDate: e.target.value }))}
                    className="w-full text-xs rounded-lg border border-[#6c6a6040] bg-[#2b2a27] text-[#eee] px-2.5 py-1.5 outline-none focus:border-[#ae5630] transition color-scheme-dark"
                  />
                </div>
                
                <div>
                  <label className="flex items-center gap-1 text-[10px] text-[#9a9893] mb-1 font-medium">
                    <Calendar size={10} />
                    Hasta (Fecha de Fin)
                  </label>
                  <input
                    type="date"
                    value={filters.endDate}
                    onChange={(e) => setFilters((prev) => ({ ...prev, endDate: e.target.value }))}
                    className="w-full text-xs rounded-lg border border-[#6c6a6040] bg-[#2b2a27] text-[#eee] px-2.5 py-1.5 outline-none focus:border-[#ae5630] transition color-scheme-dark"
                  />
                </div>

                <div>
                  <label className="flex items-center gap-1 text-[10px] text-[#9a9893] mb-1 font-medium">
                    <User size={10} />
                    Usuarios de Twitter
                  </label>
                  <input
                    type="text"
                    placeholder="elonmusk, saylor"
                    value={filters.userHandles}
                    onChange={(e) => setFilters((prev) => ({ ...prev, userHandles: e.target.value }))}
                    className="w-full text-xs placeholder:text-[#6b6a68] rounded-lg border border-[#6c6a6040] bg-[#2b2a27] text-[#eee] px-2.5 py-1.5 outline-none focus:border-[#ae5630] transition"
                  />
                </div>
              </div>

              {hasActiveFilters && (
                <button
                  onClick={handleClearFilters}
                  className="w-full text-center text-[10px] text-[#ae5630] hover:text-[#c4633a] underline font-medium transition pt-1"
                >
                  Limpiar filtros activos
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full bg-[#F5F5F0] dark:bg-[#2b2a27] relative">
        {/* Toggle Sidebar Button (when sidebar is closed) */}
        {!sidebarOpen && (
          <div className="absolute left-4 top-4 z-10">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 rounded-xl bg-[#1f1e1b] hover:bg-[#393937] text-[#b8b5a9] hover:text-white transition shadow-md flex items-center justify-center"
              title="Abrir historial"
            >
              <Menu size={18} />
            </button>
          </div>
        )}

        <ThreadPrimitive.Root className="flex h-full flex-col items-stretch p-4 pt-10 font-serif text-[#1a1a18] dark:bg-[#2b2a27] dark:text-[#eee]">
          <ThreadPrimitive.Viewport className="flex grow flex-col overflow-y-auto">
            <AuiIf condition={(s) => s.thread.isEmpty}>
              <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-2 pb-12">
                <div className="text-center font-sans">
                  <div className="text-xs uppercase tracking-[0.24em] text-[#9a9893] font-bold">
                    Portfolio RAG Agent
                  </div>
                  <h1 className="mt-4 text-4xl font-serif text-[#1a1a18] dark:text-[#f1efe8]">
                    Fintwit RAG Bot
                  </h1>
                  <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-[#6b6a68] dark:text-[#b8b5a9]">
                    Explorá y analizá tweets financieros utilizando búsqueda semántica avanzada. 
                    Configurá filtros por usuario y rango de fechas en la barra lateral para guiar la respuesta del LLM.
                  </p>
                </div>

                <div className="mt-8 grid gap-3 font-sans">
                  {SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      className="rounded-2xl border border-[#00000015] bg-white px-4 py-3.5 text-left text-sm text-[#1a1a18] transition hover:bg-[#f8f7f3] dark:border-[#6c6a6040] dark:bg-[#1f1e1b] dark:text-[#f1efe8] dark:hover:bg-[#252421] hover:scale-[1.01] duration-200 shadow-sm"
                      onClick={() => onSuggestionClick(suggestion)}
                      type="button"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            </AuiIf>

            <ThreadPrimitive.Messages
              components={{
                Message: () => <ChatMessage />,
              }}
            />

            {isLoading && (
              <div className="mx-auto mt-6 flex w-full max-w-3xl items-center gap-3 px-2 text-sm text-[#8a8985] dark:text-[#b8b5a9] font-sans">
                <Sparkles className="h-4 w-4 animate-spin text-[#ae5630]" />
                <span className="shimmer shimmer-invert shimmer-duration-1500 shimmer-repeat-delay-0 font-medium">
                  Buscando tweets y sintetizando respuesta...
                </span>
              </div>
            )}

            <div aria-hidden="true" className="h-4" />
          </ThreadPrimitive.Viewport>

          {/* Active Filter Badges display */}
          {hasActiveFilters && (
            <div className="mx-auto mb-2 flex w-full max-w-3xl flex-wrap gap-2 px-2 font-sans text-xs">
              <span className="text-[#9a9893] self-center">Filtros activos:</span>
              {filters.startDate && (
                <span className="flex items-center gap-1 rounded-lg bg-[#ae5630]/10 border border-[#ae5630]/30 text-[#eee] px-2 py-0.5">
                  <Calendar size={10} />
                  Desde: {filters.startDate}
                </span>
              )}
              {filters.endDate && (
                <span className="flex items-center gap-1 rounded-lg bg-[#ae5630]/10 border border-[#ae5630]/30 text-[#eee] px-2 py-0.5">
                  <Calendar size={10} />
                  Hasta: {filters.endDate}
                </span>
              )}
              {filters.userHandles && (
                <span className="flex items-center gap-1 rounded-lg bg-[#ae5630]/10 border border-[#ae5630]/30 text-[#eee] px-2 py-0.5">
                  <User size={10} />
                  Cuentas: {filters.userHandles}
                </span>
              )}
              <button
                onClick={handleClearFilters}
                className="text-[#9a9893] hover:text-[#eee] transition self-center ml-1"
                title="Limpiar filtros"
              >
                <Cross2Icon />
              </button>
            </div>
          )}

          {error && (
            <div className="mx-auto mb-3 w-full max-w-3xl rounded-xl border border-[#d97c66]/30 bg-[#d97c66]/10 px-4 py-3 text-sm text-[#f3c3b7] font-sans">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 text-[#d97c66]" />
                <span>{error.message}</span>
              </div>
            </div>
          )}

          <ComposerPrimitive.Root className="mx-auto flex w-full max-w-3xl flex-col rounded-2xl border border-transparent bg-white p-0.5 shadow-[0_0.25rem_1.25rem_rgba(0,0,0,0.035),0_0_0_0.5px_rgba(0,0,0,0.08)] transition-shadow duration-200 focus-within:shadow-[0_0.25rem_1.25rem_rgba(0,0,0,0.075),0_0_0_0.5px_rgba(0,0,0,0.15)] hover:shadow-[0_0.25rem_1.25rem_rgba(0,0,0,0.05),0_0_0_0.5px_rgba(0,0,0,0.12)] dark:bg-[#1f1e1b] dark:shadow-[0_0.25rem_1.25rem_rgba(0,0,0,0.4),0_0_0_0.5px_rgba(108,106,96,0.15)] dark:hover:shadow-[0_0.25rem_1.25rem_rgba(0,0,0,0.4),0_0_0_0.5px_rgba(108,106,96,0.3)] dark:focus-within:shadow-[0_0.25rem_1.25rem_rgba(0,0,0,0.5),0_0_0_0.5px_rgba(108,106,96,0.3)]">
            <div className="m-3.5 flex flex-col gap-3.5 font-sans">
              <div className="relative">
                <div className="max-h-96 w-full overflow-y-auto">
                  <ComposerPrimitive.Input
                    className="block min-h-6 w-full resize-none bg-transparent text-[#1a1a18] outline-none placeholder:text-[#9a9893] dark:text-[#eee] dark:placeholder:text-[#9a9893] text-sm"
                    placeholder="Consultá tweets o tendencias financieras..."
                  />
                </div>
              </div>

              <div className="flex w-full items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] tracking-wider text-[#9a9893] uppercase bg-[#2b2a27] border border-[#6c6a6040] rounded px-2 py-0.5">
                    Fintwit-RAG Model v1
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  {!isLoading && (
                    <ComposerPrimitive.Send className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#ae5630] transition-colors hover:bg-[#c4633a] active:scale-95 disabled:pointer-events-none disabled:opacity-50 dark:bg-[#ae5630] dark:hover:bg-[#c4633a]">
                      <ArrowUpIcon className="text-white" height={16} width={16} />
                    </ComposerPrimitive.Send>
                  )}

                  {isLoading && (
                    <button
                      className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#5f5b53] transition-colors hover:bg-[#716c63] active:scale-95"
                      onClick={onCancel}
                      type="button"
                    >
                      <StopIcon className="text-white" height={14} width={14} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          </ComposerPrimitive.Root>
        </ThreadPrimitive.Root>
      </div>
    </div>
  );
}

const ChatMessage = () => {
  const hasText = useAuiState((state) =>
    state.message.content.some(
      (part) => part.type === "text" && part.text.trim().length > 0,
    ),
  );
  const hasRenderableContent = useAuiState((state) =>
    state.message.content.some((part) => {
      if (part.type === "text") return part.text.trim().length > 0;
      return (
        part.type === "reasoning" ||
        part.type === "tool-call" ||
        part.type === "image"
      );
    }),
  );

  return (
    <MessagePrimitive.Root className="group relative mx-auto my-3 block w-full max-w-3xl">
      <AuiIf condition={(state) => state.message.role === "user"}>
        <div className="group/user relative inline-flex max-w-[75ch] flex-col gap-2 rounded-xl bg-[#DDD9CE] py-3 pl-3 pr-8 text-[#1a1a18] transition-all dark:bg-[#393937] dark:text-[#eee] font-sans text-sm ml-auto mr-0 self-end shadow-sm">
          <div className="relative flex flex-row gap-2.5">
            <div className="flex h-6 w-6 shrink-0 select-none items-center justify-center rounded-full bg-[#1a1a18] text-[10px] font-bold text-white dark:bg-[#ae5630] dark:text-white">
              U
            </div>
            <div className="flex-1">
              <div className="relative grid grid-cols-1 gap-2">
                <div className="whitespace-pre-wrap leading-relaxed">
                  <MessagePrimitive.Parts components={{ Text: MarkdownText }} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </AuiIf>

      <AuiIf condition={(state) => state.message.role === "assistant"}>
        <div className="relative mb-14 font-serif">
          <div className="relative leading-[1.75rem]">
            <div className="grid grid-cols-1 gap-2.5">
              <div className="whitespace-normal px-2 pr-8 font-serif text-[15px] text-[#1a1a18] dark:text-[#f1efe8]">
                {hasRenderableContent && (
                  <MessagePrimitive.Parts
                    components={{
                      ChainOfThought: ClaudeChainOfThought,
                      Text: MarkdownText,
                    }}
                  />
                )}
              </div>
            </div>
          </div>

          {hasText && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0">
              <ActionBarPrimitive.Root
                autohide="not-last"
                className="pointer-events-auto flex w-full translate-y-full flex-col items-end px-2 pt-2 transition"
              >
                <div className="flex items-center text-[#6b6a68] dark:text-[#9a9893] font-sans">
                  <ActionBarPrimitive.Copy className="flex h-8 w-8 items-center justify-center rounded-md transition duration-300 ease-[cubic-bezier(0.165,0.85,0.45,1)] hover:bg-transparent active:scale-95 hover:text-[#eee]">
                    <ClipboardIcon height={18} width={18} />
                  </ActionBarPrimitive.Copy>
                  <ActionBarPrimitive.FeedbackPositive className="flex h-8 w-8 items-center justify-center rounded-md transition duration-300 ease-[cubic-bezier(0.165,0.85,0.45,1)] hover:bg-transparent active:scale-95 hover:text-[#eee]">
                    <ThumbsUp height={14} width={14} />
                  </ActionBarPrimitive.FeedbackPositive>
                  <ActionBarPrimitive.FeedbackNegative className="flex h-8 w-8 items-center justify-center rounded-md transition duration-300 ease-[cubic-bezier(0.165,0.85,0.45,1)] hover:bg-transparent active:scale-95 hover:text-[#eee]">
                    <ThumbsDown height={14} width={14} />
                  </ActionBarPrimitive.FeedbackNegative>
                </div>
                <AuiIf condition={(state) => state.message.isLast}>
                  <p className="mt-2 w-full text-right text-[10px] font-sans text-[#8a8985] opacity-80 dark:text-[#9a9893] sm:text-[11px]">
                    Fintwit-RAG Bot. Datos históricos e interpretaciones sujetas a validación.
                  </p>
                </AuiIf>
              </ActionBarPrimitive.Root>
            </div>
          )}
        </div>
      </AuiIf>
    </MessagePrimitive.Root>
  );
};

const ClaudeReasoning: ReasoningMessagePartComponent = ({ text }) => {
  return (
    <div className="whitespace-pre-wrap text-sm leading-6 text-[#6b6a68] italic dark:text-[#b8b5a9]">
      {text}
    </div>
  );
};

function formatToolValue(value: unknown) {
  if (typeof value === "string") return value;

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

const ClaudeToolCall: ToolCallMessagePartComponent = ({
  argsText,
  isError,
  result,
  status,
  toolName,
}) => {
  const statusLabel =
    status.type === "running"
      ? "Ejecutando"
      : isError
        ? "Error"
        : result !== undefined
          ? "Completado"
          : "Pendiente";

  return (
    <div className="rounded-2xl border border-[#00000012] bg-white/80 shadow-sm dark:border-[#6c6a6040] dark:bg-[#1f1e1b] font-sans">
      <div className="flex items-center justify-between gap-3 border-b border-[#00000010] px-4 py-2.5 dark:border-[#6c6a6030]">
        <div className="flex items-center gap-2 text-xs font-semibold text-[#1a1a18] dark:text-[#f1efe8]">
          <MixerHorizontalIcon height={14} width={14} />
          <span>{toolName}</span>
        </div>
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#8a8985] dark:text-[#9a9893]">
          {statusLabel}
        </span>
      </div>

      <div className="space-y-3 px-4 py-3">
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.18em] text-[#8a8985] dark:text-[#9a9893]">
            Parámetros
          </div>
          <pre className="overflow-x-auto rounded-xl bg-[#f8f7f3] p-3 text-xs leading-5 text-[#4e4c48] dark:bg-[#2b2a27] dark:text-[#d8d5cb]">
            {argsText}
          </pre>
        </div>

        {result !== undefined && (
          <div>
            <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.18em] text-[#8a8985] dark:text-[#9a9893]">
              Resultados
            </div>
            <pre className="overflow-x-auto rounded-xl bg-[#f8f7f3] p-3 text-xs leading-5 text-[#4e4c48] dark:bg-[#2b2a27] dark:text-[#d8d5cb]">
              {formatToolValue(result)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};

const ClaudeChainOfThought: FC = () => {
  const aui = useAui();
  const collapsed = useAuiState((state) => state.chainOfThought.collapsed);
  const [isUsingDefaultOpenState, setIsUsingDefaultOpenState] = useState(true);
  const isExpanded = isUsingDefaultOpenState ? true : !collapsed;

  const onToggle = useCallback(() => {
    if (isUsingDefaultOpenState) {
      setIsUsingDefaultOpenState(false);
      return;
    }

    aui.chainOfThought().setCollapsed(!collapsed);
  }, [aui, collapsed, isUsingDefaultOpenState]);

  return (
    <ChainOfThoughtPrimitive.Root className="mb-4 overflow-hidden rounded-2xl border border-[#00000012] bg-[#ede9dc]/60 dark:border-[#6c6a6040] dark:bg-[#242320] font-sans">
      <button
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm text-[#5f5b53] transition hover:bg-[#e7e1d1]/70 dark:text-[#b8b5a9] dark:hover:bg-[#2b2a27]"
        onClick={onToggle}
        type="button"
      >
        {isExpanded ? (
          <ChevronDownIcon className="shrink-0" height={16} width={16} />
        ) : (
          <ChevronRightIcon className="shrink-0" height={16} width={16} />
        )}
        <Sparkles className="h-4 w-4 shrink-0" />
        <span className="font-semibold text-xs tracking-wider uppercase">Proceso de Análisis (COT)</span>
      </button>

      {isExpanded && (
        <div className="border-t border-[#00000010] px-4 py-3 dark:border-[#6c6a6030]">
          <ChainOfThoughtPrimitive.Parts
            components={{
              Layout: ({ children }) => (
                <div className="mb-3 last:mb-0">{children}</div>
              ),
              Reasoning: ClaudeReasoning,
              tools: {
                Fallback: ClaudeToolCall,
              },
            }}
          />
        </div>
      )}
    </ChainOfThoughtPrimitive.Root>
  );
};
