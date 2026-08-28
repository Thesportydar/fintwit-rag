"use client";

import { useState } from "react";
import { Claude } from "./claude";
import { useMyThreads, type ThreadItem } from "./MyRuntimeProvider";

export interface FilterSettings {
  startDate: string;
  endDate: string;
  userHandles: string;
}

export function MyAssistant() {
  const { threads, currentThreadId, onSelectThread, onNewThread, onDeleteThread, onAppendMessage } = useMyThreads();
  const [filters, setFilters] = useState<FilterSettings>({
    startDate: "",
    endDate: "",
    userHandles: "",
  });

  return (
    <Claude
      error={null}
      isLoading={false}
      threadId={currentThreadId}
      threads={threads}
      onSelectThread={onSelectThread}
      onNewThread={onNewThread}
      onDeleteThread={onDeleteThread}
      filters={filters}
      setFilters={setFilters}
      onCancel={() => {}}
      onSuggestionClick={(prompt: string) => {
        onAppendMessage(prompt);
      }}
    />
  );
}
