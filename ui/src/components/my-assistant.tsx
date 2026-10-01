"use client";

import { Claude } from "./claude";
import { useMyThreads } from "./MyRuntimeProvider";
import { useAui, useAuiState } from "@assistant-ui/react";

export function MyAssistant() {
  const {
    threads,
    currentThreadId,
    onSelectThread,
    onNewThread,
    onDeleteThread,
    onAppendMessage,
    filters,
    setFilters,
  } = useMyThreads();
  const aui = useAui();
  const isLoading = useAuiState((state) => state.thread.isRunning);

  return (
    <Claude
      error={null}
      isLoading={isLoading}
      threadId={currentThreadId}
      threads={threads}
      onSelectThread={onSelectThread}
      onNewThread={onNewThread}
      onDeleteThread={onDeleteThread}
      filters={filters}
      setFilters={setFilters}
      onCancel={() => aui.thread().cancelRun()}
      onSuggestionClick={(prompt: string) => {
        onAppendMessage(prompt);
      }}
    />
  );
}
