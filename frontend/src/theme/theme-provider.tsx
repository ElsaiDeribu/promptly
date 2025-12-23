import type { ReactNode } from 'react';

import { useState, useEffect, useContext, createContext } from 'react';

import { getStorage, useLocalStorage } from '../hooks/use-local-storage';

import type { Theme } from './types';

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export default function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('light');
  const { update } = useLocalStorage('theme', { currentTheme: theme });

  // Add a class to block transitions during theme changes
  const blockTransitions = () => {
    document.documentElement.classList.add('block-transitions');
    setTimeout(() => {
      document.documentElement.classList.remove('block-transitions');
    }, 100);
  };

  const applyTheme = (newTheme: Theme) => {
    blockTransitions();

    // Remove existing theme classes
    document.documentElement.classList.remove('dark', 'blue');

    // Add new theme class if not light theme
    if (newTheme !== 'light') {
      document.documentElement.classList.add(newTheme);
    }

    setThemeState(newTheme);
  };

  const setTheme = (newTheme: Theme) => {
    applyTheme(newTheme);
    update('currentTheme', newTheme);
  };

  // Listen for storage changes
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'theme') {
        const newTheme = JSON.parse(e.newValue || '{}');
        if (newTheme.currentTheme && newTheme.currentTheme !== theme) {
          applyTheme(newTheme.currentTheme as Theme);
        }
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);

  // Handle initial theme setup
  useEffect(() => {
    const savedTheme = getStorage('theme');
    let initialTheme: Theme = 'light';

    if (savedTheme) {
      initialTheme = savedTheme.currentTheme || 'light';
    } else {
      // If no saved theme, use system preference
      const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      initialTheme = systemPrefersDark ? 'dark' : 'light';
    }

    applyTheme(initialTheme);

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Listen for system color scheme changes
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const handleSystemThemeChange = (e: MediaQueryListEvent) => {
      const savedTheme = getStorage('theme');
      // Only update if there's no saved theme preference
      if (!savedTheme) {
        const newTheme: Theme = e.matches ? 'dark' : 'light';
        applyTheme(newTheme);
      }
    };

    mediaQuery.addEventListener('change', handleSystemThemeChange);
    return () => mediaQuery.removeEventListener('change', handleSystemThemeChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Add the necessary style on component mount
  useEffect(() => {
    const style = document.createElement('style');
    style.innerHTML = `
      .block-transitions * {
        transition: none !important;
      }
    `;
    document.head.appendChild(style);

    return () => {
      document.head.removeChild(style);
    };
  }, []);

  const value = {
    theme,
    setTheme,
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
