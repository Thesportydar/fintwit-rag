"use client";

import type { AnchorHTMLAttributes, ReactNode } from "react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";

const EVIDENCE_TAG = /\[evidence:tweet:(\d+)\]/g;
// Tag parcial al final del texto mientras se esta streameando (ej: "[evidence:tw")
const PARTIAL_EVIDENCE_TAIL = /\[(?:e(?:v(?:i(?:d(?:e(?:n(?:c(?:e(?::(?:t(?:w(?:e(?:e(?:t(?::\d*)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?$/;
const EVIDENCE_HASH = "#evidence";

/** Convierte [evidence:tweet:ID] en links markdown numerados hacia el tweet en X. */
function linkifyEvidence(text: string): string {
  const order = new Map<string, number>();
  return text
    .replace(PARTIAL_EVIDENCE_TAIL, "")
    .replace(EVIDENCE_TAG, (_, id: string) => {
      if (!order.has(id)) order.set(id, order.size + 1);
      return `[${order.get(id)}](https://x.com/i/status/${id}${EVIDENCE_HASH})`;
    });
}

function XLogo() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-2.5 w-2.5 fill-current">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  );
}

function MarkdownLink({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) {
  if (href?.endsWith(EVIDENCE_HASH)) {
    return (
      <a
        href={href.slice(0, -EVIDENCE_HASH.length)}
        target="_blank"
        rel="noopener noreferrer"
        title="Ver tweet en X"
        aria-label={`Ver tweet ${children} en X`}
        className="mx-0.5 inline-flex h-4 items-center gap-0.5 rounded-full border border-zinc-600/60 bg-zinc-700/40 px-1.5 align-middle text-[0.65rem] leading-none text-zinc-300 no-underline transition-colors hover:border-zinc-400 hover:bg-zinc-600/60 hover:text-white"
      >
        <XLogo />
        <span>{children}</span>
      </a>
    );
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
      {children}
    </a>
  );
}

/** La nota legal final ("Nota: ...") se muestra en cursiva y gris, como pie de la respuesta. */
function MarkdownParagraph({ children }: { children?: ReactNode }) {
  const first = Array.isArray(children) ? children[0] : children;
  if (typeof first === "string" && first.trimStart().startsWith("Nota:")) {
    return <p className="mt-3 text-xs italic text-zinc-500">{children}</p>;
  }
  return <p>{children}</p>;
}

export function MarkdownText() {
  return (
    <MarkdownTextPrimitive
      preprocess={linkifyEvidence}
      components={{ a: MarkdownLink, p: MarkdownParagraph }}
      className="prose prose-invert prose-p:my-0 prose-pre:my-3 prose-code:text-[0.9em] max-w-none"
    />
  );
}
