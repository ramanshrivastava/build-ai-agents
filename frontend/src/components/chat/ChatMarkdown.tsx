import ReactMarkdown from "react-markdown";

interface ChatMarkdownProps {
  text: string;
}

/**
 * Assistant text rendered as markdown at chat density — tight margins,
 * document-like (no bubble), with mono inline code and quiet list styling.
 */
export function ChatMarkdown({ text }: ChatMarkdownProps) {
  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => (
          <p className="my-2 leading-relaxed">{children}</p>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold text-foreground">{children}</strong>
        ),
        em: ({ children }) => <em className="italic">{children}</em>,
        ul: ({ children }) => (
          <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>
        ),
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        code: ({ children }) => (
          <code className="rounded bg-foreground/[0.06] px-1 py-0.5 font-mono text-[12px]">
            {children}
          </code>
        ),
        pre: ({ children }) => (
          <pre className="my-2 overflow-x-auto rounded-md bg-foreground/[0.04] p-3 font-mono text-[12px] leading-relaxed">
            {children}
          </pre>
        ),
        h1: ({ children }) => (
          <p className="my-2 text-sm font-semibold">{children}</p>
        ),
        h2: ({ children }) => (
          <p className="my-2 text-sm font-semibold">{children}</p>
        ),
        h3: ({ children }) => (
          <p className="my-2 text-sm font-semibold">{children}</p>
        ),
        a: ({ children, href }) => (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="underline decoration-amber-500/50 underline-offset-2 hover:text-amber-500"
          >
            {children}
          </a>
        ),
        blockquote: ({ children }) => (
          <blockquote className="my-2 border-l-2 border-amber-500/40 pl-3 italic text-muted-foreground">
            {children}
          </blockquote>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
