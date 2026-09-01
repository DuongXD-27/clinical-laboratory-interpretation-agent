import { ExternalLink } from "lucide-react";

import { publicSourceLabel } from "@/lib/citationUi.mjs";

export default function ChatSources({ sources }: { sources: string[] }) {
  if (sources.length === 0) return null;

  return (
    <details className="assistant-sources">
      <summary>Nguồn tham khảo ({sources.length})</summary>
      <ol>
        {sources.map((source) => {
          const hostname = new URL(source).hostname.replace(/^www\./, "");
          return (
            <li key={source}>
              <a
                href={source}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Mở nguồn ${hostname} trong thẻ mới`}
              >
                <span>{publicSourceLabel(source)}</span>
                <small>{hostname}</small>
                <ExternalLink aria-hidden="true" />
              </a>
            </li>
          );
        })}
      </ol>
    </details>
  );
}
