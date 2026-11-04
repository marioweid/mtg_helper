import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

const STYLES =
  "min-w-0 space-y-4 break-words text-sm leading-7 text-gray-200 " +
  "[&_h1]:text-xl [&_h2]:text-lg [&_h3]:text-base " +
  "[&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold " +
  "[&_h4]:font-semibold [&_h5]:font-semibold [&_h6]:font-semibold " +
  "[&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-6 [&_ol]:pl-6 [&_li]:my-1 " +
  "[&_li>ul]:mt-1 [&_li>ol]:mt-1 [&_strong]:font-semibold " +
  "[&_a]:text-indigo-300 [&_a]:underline [&_a]:underline-offset-2 " +
  "[&_code]:rounded [&_code]:bg-white/5 [&_code]:px-1 " +
  "[&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-black/20 [&_pre]:p-4 " +
  "[&_blockquote]:border-l-2 [&_blockquote]:border-indigo-400/40 [&_blockquote]:pl-4 " +
  "[&_th]:border [&_th]:border-white/15 [&_th]:px-3 [&_th]:py-2 " +
  "[&_td]:border [&_td]:border-white/10 [&_td]:px-3 [&_td]:py-2 " +
  "[&_hr]:border-white/15";

export function TutorMarkdown({ children }: { children: string }) {
  return (
    <div className={STYLES}>
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        disallowedElements={["img"]}
        components={{
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="max-w-full overflow-x-auto">
              <table className="w-full border-collapse text-left">{children}</table>
            </div>
          ),
        }}
      >
        {children}
      </Markdown>
    </div>
  );
}
