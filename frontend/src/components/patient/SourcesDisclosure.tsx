import { sourceHostname } from "@/lib/patientUi.mjs";
import { citationContext, citationLabel } from "@/lib/citationUi.mjs";
import type { Citation } from "@/types/analysis";

type Props = {
  sources?: string[];
  citations?: Citation[];
};

export default function SourcesDisclosure({ sources = [], citations = [] }: Props) {
  const sourceCount = citations.length || sources.length;
  if (sourceCount === 0) return null;

  return (
    <details className="sources-disclosure">
      <summary>
        <span>Nguồn tham khảo · {sourceCount} nguồn</span>
        <span className="sources-action">Xem nguồn</span>
      </summary>
      <ol>
        {citations.map((citation, index) => (
          <li key={`${citation.source_id}-${citation.url}-${index}`}>
            <a href={citation.url} target="_blank" rel="noopener noreferrer">
              {citationLabel(citation)}
            </a>
            {citationContext(citation) && <small className="block text-slate-500">{citationContext(citation)}</small>}
          </li>
        ))}
        {citations.length === 0 && sources.map((source, index) => (
          <li key={`${source}-${index}`}>
            <a href={source} target="_blank" rel="noopener noreferrer">
              {sourceHostname(source)}
            </a>
          </li>
        ))}
      </ol>
    </details>
  );
}
