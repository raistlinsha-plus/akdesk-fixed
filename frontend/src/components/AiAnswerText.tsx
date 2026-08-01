import type { ReactNode } from "react";

function inline(text: string): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
    .map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={`${index}-${part}`}>{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith("`") && part.endsWith("`")) {
        return <code key={`${index}-${part}`}>{part.slice(1, -1)}</code>;
      }
      return part;
    });
}

export function AiAnswerText({ text }: { text: string }) {
  return (
    <div className="ai-answer-text">
      {text.split(/\r?\n/).map((rawLine, index) => {
        const line = rawLine.trim();
        if (!line) return <span className="ai-answer-spacer" key={index} />;
        if (/^-{3,}$/.test(line)) return <hr key={index} />;
        if (line.startsWith("> ")) {
          return <blockquote key={index}>{inline(line.slice(2))}</blockquote>;
        }
        const heading = line.match(/^#{1,3}\s+(.+)$/);
        if (heading) {
          return <h4 key={index}>{inline(heading[1])}</h4>;
        }
        const listItem = line.match(/^(\d+\.|[-*])\s+(.+)$/);
        if (listItem) {
          return (
            <div className="ai-answer-list-item" key={index}>
              <span>{listItem[1]}</span>
              <p>{inline(listItem[2])}</p>
            </div>
          );
        }
        return <p key={index}>{inline(line)}</p>;
      })}
    </div>
  );
}
