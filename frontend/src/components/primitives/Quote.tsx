import React from 'react';

interface HighlightedQuoteProps {
  quote: string;
  sourceCase?: string;
  sourceDate?: string;
  startOffset?: number;
  endOffset?: number;
  className?: string;
  onClick?: () => void;
}

export const HighlightedQuote: React.FC<HighlightedQuoteProps> = ({
  quote,
  sourceCase,
  sourceDate,
  startOffset,
  endOffset,
  className = '',
  onClick,
}) => {
  return (
    <div
      onClick={onClick}
      className={`border-l-2 border-[var(--accent-oxblood)] pl-3 py-1 my-2 bg-[var(--highlight-pen)] text-[var(--highlight-pen-text)] ${className}`}
    >
      <blockquote className="font-serif text-[13px] leading-relaxed italic">
        &ldquo;{quote}&rdquo;
      </blockquote>
      {(sourceCase || sourceDate || startOffset !== undefined) && (
        <div className="font-mono text-[10px] text-[var(--ink-secondary)] mt-1 flex items-center gap-2 flex-wrap">
          {sourceCase && <span className="font-semibold">{sourceCase}</span>}
          {sourceDate && <span>({sourceDate})</span>}
          {startOffset !== undefined && (
            <span className="text-[9px] text-[var(--ink-muted)]">
              chars {startOffset}–{endOffset}
            </span>
          )}
        </div>
      )}
    </div>
  );
};

