import { ReactNode, useEffect, useMemo, useState } from 'react';

import { logout, type AuthUser } from '../api';
import { setSessionToken } from '../auth';
import { applyTheme, getTheme, setTheme, toggleTheme, type Theme } from '../theme';

type NavItem<T extends string> = {
  id: T;
  label: string;
  group: string;
};

type Props<T extends string> = {
  page: T;
  navItems: NavItem<T>[];
  onNavigate: (page: T) => void;
  user: AuthUser;
  onLoggedOut: () => void;
  children: ReactNode;
};

function defaultOpenGroups<T extends string>(navItems: NavItem<T>[], activePage: T): Record<string, boolean> {
  const groups = Array.from(new Set(navItems.map((item) => item.group)));
  const current = navItems.find((item) => item.id === activePage)?.group;
  const out: Record<string, boolean> = {};
  groups.forEach((g) => {
    out[g] = g === current;
  });
  return out;
}

export default function AppShell<T extends string>({ page, navItems, onNavigate, user, onLoggedOut, children }: Props<T>) {
  const [theme, setLocalTheme] = useState<Theme>(getTheme());
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => defaultOpenGroups(navItems, page));

  const groups = useMemo(() => Array.from(new Set(navItems.map((item) => item.group))), [navItems]);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    const g = navItems.find((item) => item.id === page)?.group;
    if (g) {
      setOpenGroups((prev) => ({ ...prev, [g]: true }));
    }
  }, [page, navItems]);

  const onToggleTheme = () => {
    const next = toggleTheme(theme);
    setLocalTheme(next);
    setTheme(next);
  };

  const onLogout = async () => {
    await logout().catch(() => undefined);
    setSessionToken('');
    onLoggedOut();
  };

  const toggleGroup = (group: string) => {
    setOpenGroups((prev) => ({ ...prev, [group]: !prev[group] }));
  };

  return (
    <div className="site-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <img className="brand-logo" src="/negotium-logo.png" alt="Negotium" />
          <div>
            <p className="eyebrow">Negotium</p>
            <strong>AI Office BPA</strong>
          </div>
        </div>
        <div className="topbar-actions">
          <button
            type="button"
            className="theme-toggle"
            onClick={onToggleTheme}
            aria-label="테마 전환"
            title={theme === 'dark' ? '라이트 모드' : '다크 모드'}
          >
            {theme === 'dark' ? '라이트 모드' : '다크 모드'}
          </button>
          <span className="user-picker">현재 사용자: {user.display_name || user.id}</span>
          <button className="secondary-button" type="button" onClick={() => void onLogout()}>
            로그아웃
          </button>
        </div>
      </header>

      <div className="layout-grid">
        <aside className="sidebar">
          {groups.map((group) => (
            <section key={group} className="nav-group">
              <button
                type="button"
                className="nav-group-header"
                aria-expanded={Boolean(openGroups[group])}
                onClick={() => toggleGroup(group)}
              >
                <span>{group}</span>
                <span className="nav-group-chevron" aria-hidden>
                  {openGroups[group] ? '▼' : '▶'}
                </span>
              </button>
              {openGroups[group] ? (
                <div className="nav-group-items">
                  {navItems
                    .filter((item) => item.group === group)
                    .map((item) => (
                      <button
                        className={page === item.id ? 'active-tab' : 'secondary-button'}
                        key={item.id}
                        type="button"
                        onClick={() => onNavigate(item.id)}
                      >
                        {item.label}
                      </button>
                    ))}
                </div>
              ) : null}
            </section>
          ))}
        </aside>
        <main className="content-panel">{children}</main>
      </div>
    </div>
  );
}
