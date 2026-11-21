import { Sparkles } from 'lucide-react';

export const APP_NAME = 'Star Dust';

/**
 * Product mark: a navy sparkle on the orange accent tile (the accent's one fixed use).
 * `light` is for navy/dark backgrounds; `compact` hides the name below the md breakpoint
 * (collapsed sidebar on phones).
 */
export function Logo({ size = 'md', light = false, compact = false }) {
  const box = size === 'lg' ? 'p-2' : 'p-1.5';
  const icon = size === 'lg' ? 'h-7 w-7' : 'h-5 w-5';
  return (
    <div className="flex items-center gap-2.5">
      <div className={`rounded-lg bg-accent ${box}`}>
        <Sparkles className={`${icon} text-navy-900`} />
      </div>
      <span
        className={`${size === 'lg' ? 'text-2xl' : 'text-lg'} font-bold tracking-tight ${light ? 'text-white' : 'text-navy'} ${compact ? 'hidden md:inline' : ''}`}
      >
        {APP_NAME}
      </span>
    </div>
  );
}
