import { sourceHostname } from "@/lib/patientUi.mjs";

type Props = {
  sources?: string[];
};

export default function SourcesDisclosure({ sources = [] }: Props) {
  if (sources.length === 0) return null;

  return (
    <details className="sources-disclosure">
      <summary>
        <span>Nguồn tham khảo · {sources.length} nguồn</span>
        <span className="sources-action">Xem nguồn</span>
      </summary>
      <ol>
        {sources.map((source, index) => (
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
