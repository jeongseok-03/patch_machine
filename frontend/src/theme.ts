export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'pm-theme';

export function getTheme(): Theme {
  if (typeof window === 'undefined') {
    return 'light';
  }
  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (saved === 'light' || saved === 'dark') {
    return saved;
  }
  return 'light';
}

export function applyTheme(theme: Theme): void {
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = theme;
  }
}

export function setTheme(theme: Theme): void {
  applyTheme(theme);
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, theme);
  }
}

export function toggleTheme(current: Theme): Theme {
  return current === 'dark' ? 'light' : 'dark';
}
