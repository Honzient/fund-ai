import { useMemo } from 'react';
import MarkdownIt from 'markdown-it';
import { cn } from '../utils/format';

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
});

/** Markdown 渲染（html 关闭，避免 XSS） */
export default function Markdown({ content, className }: { content: string; className?: string }) {
  const html = useMemo(() => md.render(content ?? ''), [content]);
  return (
    <div
      className={cn('markdown-body text-sm leading-relaxed', className)}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
