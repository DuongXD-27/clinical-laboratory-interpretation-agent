import { sourceHostname } from "@/lib/patientUi.mjs";
import { citationContext, citationLabel, uniqueCitations, uniqueSourceUrls } from "@/lib/citationUi.mjs";
import type { Citation } from "@/types/analysis";

type Props = {
  sources?: string[];
  citations?: Citation[];
};

export default function SourcesDisclosure({ sources = [], citations = [] }: Props) {
  const renderedCitations = uniqueCitations(citations);
  const renderedSources = uniqueSourceUrls(sources);
  const sourceCount = renderedCitations.length || renderedSources.length;
  if (sourceCount === 0) return null;

  return (
    <details className="sources-disclosure">
      <summary>
        <span>Nguồn tham khảo · {sourceCount} nguồn</span>
        <span className="sources-action">Xem nguồn</span>
      </summary>
      <ol>
        {renderedCitations.map((citation) => (
          <li key={citation.source_id || citation.url}>
            <a href={citation.url} target="_blank" rel="noopener noreferrer">
              {citationLabel(citation)}
            </a>
            {citationContext(citation) && <small className="block text-slate-500">{citationContext(citation)}</small>}
          </li>
        ))}
        {renderedCitations.length === 0 && renderedSources.map((source) => (
          <li key={source}>
            <a href={source} target="_blank" rel="noopener noreferrer">
              {sourceHostname(source)}
            </a>
          </li>
        ))}
      </ol>
    </details>
  );
}
