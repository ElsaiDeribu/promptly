import type { Theme } from '@/theme/types';

import { useTheme } from '@/theme/theme-provider';

export const ThemeToggle = () => {
  const { theme, setTheme } = useTheme();
  const themes: Theme[] = ['light', 'dark', 'blue'];

  return (
    <div className="flex gap-2">
      {themes.map((t) => (
        <button
          key={t}
          onClick={() => setTheme(t)}
          className={`px-4 py-2 rounded-md ${
            theme === t
              ? 'bg-primary text-primary-foreground'
              : 'bg-secondary text-secondary-foreground'
          }`}
        >
          {t.charAt(0).toUpperCase() + t.slice(1)}
        </button>
      ))}
    </div>
  );
};

export default ThemeToggle;
