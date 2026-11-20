import { Sparkles } from 'lucide-react';

export const APP_NAME = 'Star Dust';

/** Product mark: a sparkle on the brand colour. */
export function Logo({ size = 'md', light = false }) {
  const box = size === 'lg' ? 'p-2' : 'p-1.5';
  const icon = size === 'lg' ? 'h-7 w-7' : 'h-5 w-5';
  return (
    <div className="flex items-center gap-2">
      <div className={`rounded-lg bg-indigo-600 ${box}`}>
        <Sparkles className={`${icon} text-white`} />
      </div>
      <span className={`${size === 'lg' ? 'text-2xl' : 'text-lg'} font-bold tracking-tight ${light ? 'text-white' : 'text-gray-900'}`}>{APP_NAME}</span>
    </div>
  );
}
