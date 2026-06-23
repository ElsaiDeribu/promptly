import type { Components } from 'react-markdown';

// ----------------------------------------------------------------------

/**
 * Tailwind-styled renderers for assistant markdown output. Kept separate from
 * the chat components so the styling can be reused and tested in isolation.
 */
export const markdownComponents: Components = {
  p: ({ children }) => <p className="my-1.5 leading-relaxed">{children}</p>,
  h1: ({ children }) => <h1 className="mt-3 mb-1.5 text-lg font-bold">{children}</h1>,
  h2: ({ children }) => <h2 className="mt-3 mb-1.5 text-base font-bold">{children}</h2>,
  h3: ({ children }) => <h3 className="mt-2 mb-1 text-sm font-semibold">{children}</h3>,
  ul: ({ children }) => <ul className="my-1.5 ml-4 list-disc space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="my-1.5 ml-4 list-decimal space-y-0.5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  code: ({ className, children, ...props }) => {
    const isBlock = className?.includes('language-');
    if (isBlock) {
      return (
        <code
          className={`block my-2 overflow-x-auto rounded-md bg-black/5 p-3 text-xs dark:bg-white/10 ${className || ''}`}
          {...props}
        >
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-black/10 px-1 py-0.5 text-xs dark:bg-white/10" {...props}>
        {children}
      </code>
    );
  },
  pre: ({ children }) => <pre className="my-2 overflow-x-auto">{children}</pre>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-foreground/30 pl-3 italic opacity-80">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="min-w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-border bg-muted px-2 py-1 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline underline-offset-2 hover:opacity-80"
    >
      {children}
    </a>
  ),
  hr: () => <hr className="my-3 border-border" />,
};
