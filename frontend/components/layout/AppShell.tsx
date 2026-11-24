"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ChefHat,
  Home,
  Languages,
  LogIn,
  LogOut,
  Menu as MenuIcon,
  Mic,
  Moon,
  Package,
  Pill,
  Settings,
  ShoppingBasket,
  Stethoscope,
  Sun,
  Users,
  Utensils,
  X,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { useTheme } from "@/lib/theme";

interface NavItem {
  href: string;
  labelKey: string;
  icon: React.ComponentType<{
    className?: string;
    style?: React.CSSProperties;
    "aria-hidden"?: boolean | "true" | "false";
  }>;
}

const CARE_NAV: NavItem[] = [
  { href: "/dashboard", labelKey: "nav.dashboard", icon: Home },
  { href: "/menu", labelKey: "nav.menu", icon: Utensils },
  { href: "/log", labelKey: "nav.log", icon: Mic },
  { href: "/stock", labelKey: "nav.stock", icon: Package },
];

const FAMILY_NAV: NavItem[] = [
  { href: "/members", labelKey: "nav.members", icon: Users },
  { href: "/bazar", labelKey: "nav.bazar", icon: ShoppingBasket },
  { href: "/reminders", labelKey: "nav.reminders", icon: Pill },
  { href: "/reviews", labelKey: "nav.reviews", icon: Stethoscope },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const router = useRouter();
  const { locale, toggleLocale, t } = useI18n();
  const { resolvedTheme, toggleTheme } = useTheme();
  const { session, clearSession } = useSession();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const isPatientRoute =
    pathname.startsWith("/patient") || pathname.startsWith("/clinician");
  const isLandingOrWelcome = pathname === "/" || pathname === "/welcome";

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileMenuOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileMenuOpen]);

  if (isPatientRoute) {
    return <main className="min-h-screen">{children}</main>;
  }

  function handleSignOut() {
    clearSession();
    setMobileMenuOpen(false);
    router.push("/welcome?tab=login");
  }

  if (isLandingOrWelcome) {
    return (
      <div className="min-h-screen flex flex-col">
        <header className="glass sticky top-0 z-40 h-16 px-4 sm:px-6 flex items-center">
          <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4">
            <Link href="/" className="flex items-center gap-2.5 min-h-[42px] shrink-0">
              <span
                className="skeu-button flex h-9 w-9 items-center justify-center rounded-[11px]"
                aria-hidden="true"
              >
                <ChefHat className="h-4.5 w-4.5" />
              </span>
              <span className="font-display text-lg font-bold tracking-tight" style={{ color: "var(--text)" }}>
                {t("app.name")}
              </span>
            </Link>

            {pathname === "/" && (
              <nav className="hidden md:flex items-center gap-6" aria-label="Landing Sections">
                <a
                  href="#features"
                  className="text-sm font-medium transition-colors hover:text-[var(--accent)]"
                  style={{ color: "var(--text-muted)" }}
                >
                  {t("nav.anchorFeatures")}
                </a>
                <a
                  href="#daily-rhythm"
                  className="text-sm font-medium transition-colors hover:text-[var(--accent)]"
                  style={{ color: "var(--text-muted)" }}
                >
                  {t("nav.anchorRhythm")}
                </a>
                <a
                  href="#trust"
                  className="text-sm font-medium transition-colors hover:text-[var(--accent)]"
                  style={{ color: "var(--text-muted)" }}
                >
                  {t("nav.anchorTrust")}
                </a>
              </nav>
            )}

            <div className="flex items-center gap-2">
              <button
                type="button"
                data-testid="lang-toggle"
                onClick={toggleLocale}
                title={t("common.languageLabel")}
                className="neu-raised-sm inline-flex h-10 items-center gap-1.5 px-3 text-xs font-semibold cursor-pointer"
                style={{ color: "var(--text)" }}
              >
                <Languages className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} aria-hidden="true" />
                <span>{locale === "bn" ? "বাং → EN" : "EN → বাং"}</span>
              </button>

              <button
                type="button"
                data-testid="theme-toggle"
                onClick={toggleTheme}
                aria-label={t("common.themeLabel")}
                className="neu-raised-sm inline-flex h-10 w-10 items-center justify-center cursor-pointer"
                style={{ color: "var(--text)" }}
              >
                {resolvedTheme === "dark" ? (
                  <Sun className="h-4 w-4" style={{ color: "var(--saffron)" }} aria-hidden="true" />
                ) : (
                  <Moon className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
                )}
              </button>

              <div className="hidden md:flex items-center gap-2 pl-1">
                {session ? (
                  <Link
                    href="/dashboard"
                    className="skeu-button inline-flex h-10 items-center gap-1.5 px-4 text-xs font-semibold"
                  >
                    <span>{t("nav.openApp")}</span>
                  </Link>
                ) : (
                  <>
                    <Link
                      href="/welcome?tab=login"
                      className="neu-raised-sm inline-flex h-10 items-center px-3.5 text-xs font-semibold"
                      style={{ color: "var(--text)" }}
                    >
                      {t("nav.signIn")}
                    </Link>
                    <Link
                      href="/welcome?tab=create"
                      className="skeu-button inline-flex h-10 items-center px-4 text-xs font-semibold"
                    >
                      {t("nav.getStarted")}
                    </Link>
                  </>
                )}
              </div>

              <button
                type="button"
                data-testid="nav-hamburger"
                onClick={() => setMobileMenuOpen((v) => !v)}
                aria-expanded={mobileMenuOpen}
                aria-label={mobileMenuOpen ? t("nav.closeMenu") : t("nav.openMenu")}
                className="neu-raised-sm inline-flex md:hidden h-10 w-10 items-center justify-center cursor-pointer"
                style={{ color: "var(--text)" }}
              >
                {mobileMenuOpen ? <X className="h-4 w-4" /> : <MenuIcon className="h-4 w-4" />}
              </button>
            </div>
          </div>
        </header>

        {mobileMenuOpen && (
          <div
            className="fixed inset-0 z-50 md:hidden flex justify-start"
            style={{ backgroundColor: "rgba(24, 20, 17, 0.45)" }}
            role="dialog"
            aria-modal="true"
            aria-label={t("nav.openMenu")}
            onClick={() => setMobileMenuOpen(false)}
          >
            <div
              className="glass harbor-drawer-in h-full w-72 max-w-[85vw] p-5 flex flex-col justify-between"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <span className="font-display text-lg font-bold" style={{ color: "var(--text)" }}>
                    {t("app.name")}
                  </span>
                  <button
                    type="button"
                    onClick={() => setMobileMenuOpen(false)}
                    aria-label={t("nav.closeMenu")}
                    className="neu-raised-sm flex h-9 w-9 items-center justify-center cursor-pointer"
                    style={{ color: "var(--text)" }}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                {pathname === "/" && (
                  <nav className="flex flex-col gap-1.5" aria-label="Mobile Landing Navigation">
                    <a
                      href="#features"
                      onClick={() => setMobileMenuOpen(false)}
                      className="neu-raised-sm flex min-h-[42px] items-center px-3.5 text-sm font-semibold"
                      style={{ color: "var(--text)" }}
                    >
                      {t("nav.anchorFeatures")}
                    </a>
                    <a
                      href="#daily-rhythm"
                      onClick={() => setMobileMenuOpen(false)}
                      className="neu-raised-sm flex min-h-[42px] items-center px-3.5 text-sm font-semibold"
                      style={{ color: "var(--text)" }}
                    >
                      {t("nav.anchorRhythm")}
                    </a>
                    <a
                      href="#trust"
                      onClick={() => setMobileMenuOpen(false)}
                      className="neu-raised-sm flex min-h-[42px] items-center px-3.5 text-sm font-semibold"
                      style={{ color: "var(--text)" }}
                    >
                      {t("nav.anchorTrust")}
                    </a>
                  </nav>
                )}
              </div>

              <div className="space-y-2.5 pt-4 border-t border-[var(--border-subtle)]">
                {session ? (
                  <Link
                    href="/dashboard"
                    onClick={() => setMobileMenuOpen(false)}
                    className="skeu-button flex min-h-[42px] w-full items-center justify-center text-sm font-semibold"
                  >
                    {t("nav.openApp")}
                  </Link>
                ) : (
                  <>
                    <Link
                      href="/welcome?tab=create"
                      onClick={() => setMobileMenuOpen(false)}
                      className="skeu-button flex min-h-[42px] w-full items-center justify-center text-sm font-semibold"
                    >
                      {t("nav.getStarted")}
                    </Link>
                    <Link
                      href="/welcome?tab=login"
                      onClick={() => setMobileMenuOpen(false)}
                      className="neu-raised-sm flex min-h-[42px] w-full items-center justify-center text-sm font-semibold"
                      style={{ color: "var(--text)" }}
                    >
                      {t("nav.signIn")}
                    </Link>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 sm:px-6 py-4">{children}</main>
      </div>
    );
  }

  function renderNavLink(item: NavItem, compact: boolean) {
    const Icon = item.icon;
    const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={() => setMobileMenuOpen(false)}
        title={compact ? t(item.labelKey) : undefined}
        className={`flex min-h-[42px] items-center rounded-[12px] text-sm font-semibold transition-all ${
          compact ? "justify-center px-2" : "gap-3 px-3"
        } ${active ? "skeu-button" : "hover:bg-[var(--surface)]"}`}
        style={active ? undefined : { color: "var(--text)" }}
      >
        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
        {!compact && <span className="truncate">{t(item.labelKey)}</span>}
      </Link>
    );
  }

  const settingsActive = pathname === "/settings" || pathname.startsWith("/settings/");

  function renderSidebarContents(compact: boolean) {
    return (
      <div className="flex h-full flex-col justify-between gap-4">
        <div className="space-y-4">
          <div className="space-y-1">
            {!compact && (
              <p
                className="px-3 pb-1 text-[11px] font-bold uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                {t("nav.groupCare")}
              </p>
            )}
            <div className="space-y-1">{CARE_NAV.map((item) => renderNavLink(item, compact))}</div>
          </div>

          <div className="space-y-1">
            {!compact && (
              <p
                className="px-3 pb-1 text-[11px] font-bold uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                {t("nav.groupFamily")}
              </p>
            )}
            <div className="space-y-1">{FAMILY_NAV.map((item) => renderNavLink(item, compact))}</div>
          </div>
        </div>

        <div className="space-y-1.5 pt-3 border-t border-[var(--border-subtle)]">
          <Link
            href="/settings"
            onClick={() => setMobileMenuOpen(false)}
            title={compact ? t("nav.settings") : undefined}
            className={`flex min-h-[42px] items-center rounded-[12px] text-sm font-semibold transition-all ${
              compact ? "justify-center px-2" : "gap-3 px-3"
            } ${settingsActive ? "skeu-button" : "hover:bg-[var(--surface)]"}`}
            style={settingsActive ? undefined : { color: "var(--text)" }}
          >
            <Settings className="h-4 w-4 shrink-0" aria-hidden="true" />
            {!compact && <span className="truncate">{t("nav.settings")}</span>}
          </Link>

          {session ? (
            <button
              type="button"
              onClick={handleSignOut}
              data-testid="nav-signout"
              title={compact ? t("nav.signOut") : undefined}
              className={`flex min-h-[42px] w-full items-center rounded-[12px] text-sm font-semibold cursor-pointer transition-colors hover:bg-[var(--surface)] ${
                compact ? "justify-center px-2" : "gap-3 px-3"
              }`}
              style={{ color: "var(--danger)" }}
            >
              <LogOut className="h-4 w-4 shrink-0" aria-hidden="true" />
              {!compact && <span className="truncate">{t("nav.signOut")}</span>}
            </button>
          ) : (
            <Link
              href="/welcome?tab=login"
              onClick={() => setMobileMenuOpen(false)}
              title={compact ? t("nav.signIn") : undefined}
              className={`flex min-h-[42px] items-center rounded-[12px] text-sm font-semibold transition-colors hover:bg-[var(--surface)] ${
                compact ? "justify-center px-2" : "gap-3 px-3"
              }`}
              style={{ color: "var(--accent)" }}
            >
              <LogIn className="h-4 w-4 shrink-0" aria-hidden="true" />
              {!compact && <span className="truncate">{t("nav.signIn")}</span>}
            </Link>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Slim Glass Workspace Header with Single-Source Hamburger */}
      <header className="glass sticky top-0 z-40 h-14 px-3 sm:px-5 flex items-center">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <button
              type="button"
              data-testid="sidebar-toggle"
              aria-expanded={mobileMenuOpen || !sidebarCollapsed}
              aria-label={t("nav.toggleSidebar")}
              onClick={() => {
                if (typeof window !== "undefined" && window.innerWidth >= 1024) {
                  setSidebarCollapsed((v) => !v);
                } else {
                  setMobileMenuOpen((v) => !v);
                }
              }}
              className="neu-raised-sm inline-flex h-10 w-10 shrink-0 items-center justify-center cursor-pointer"
              style={{ color: "var(--text)" }}
            >
              <MenuIcon className="h-4 w-4" aria-hidden="true" />
            </button>

            <Link
              href={session ? "/dashboard" : "/"}
              className="flex items-center gap-2 min-h-[40px] min-w-0"
            >
              <span
                className="skeu-button flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px]"
                aria-hidden="true"
              >
                <ChefHat className="h-4 w-4" />
              </span>
              <div className="min-w-0 leading-tight">
                <span className="block font-display text-base font-bold truncate" style={{ color: "var(--text)" }}>
                  {t("app.name")}
                </span>
                {session && (
                  <span className="hidden sm:block text-[11px] truncate" style={{ color: "var(--text-muted)" }}>
                    {session.householdName} · {session.accessCode}
                  </span>
                )}
              </div>
            </Link>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              data-testid="lang-toggle"
              onClick={toggleLocale}
              title={t("common.languageLabel")}
              className="neu-raised-sm inline-flex h-10 items-center gap-1.5 px-3 text-xs font-semibold cursor-pointer"
              style={{ color: "var(--text)" }}
            >
              <Languages className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} aria-hidden="true" />
              <span>{locale === "bn" ? "বাং → EN" : "EN → বাং"}</span>
            </button>

            <button
              type="button"
              data-testid="theme-toggle"
              onClick={toggleTheme}
              aria-label={t("common.themeLabel")}
              className="neu-raised-sm inline-flex h-10 w-10 items-center justify-center cursor-pointer"
              style={{ color: "var(--text)" }}
            >
              {resolvedTheme === "dark" ? (
                <Sun className="h-4 w-4" style={{ color: "var(--saffron)" }} aria-hidden="true" />
              ) : (
                <Moon className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Workspace Container (Desktop Collapsible Sidebar + Content) */}
      <div className="mx-auto flex w-full max-w-6xl flex-1 gap-6 px-4 sm:px-5 py-6">
        <aside
          className={`hidden lg:flex shrink-0 flex-col glass rounded-[18px] p-3 self-start sticky top-20 transition-all duration-200 ${
            sidebarCollapsed ? "w-[68px]" : "w-56"
          }`}
          aria-label="Primary Navigation"
        >
          {renderSidebarContents(sidebarCollapsed)}
        </aside>

        <main className="min-w-0 flex-1 overflow-x-hidden">{children}</main>
      </div>

      {/* Mobile/Tablet Slide-Over Drawer (Zero Redundant Bottom Nav Bar) */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-50 lg:hidden flex justify-start"
          style={{ backgroundColor: "rgba(24, 20, 17, 0.48)" }}
          role="dialog"
          aria-modal="true"
          aria-label={t("nav.openMenu")}
          onClick={() => setMobileMenuOpen(false)}
        >
          <aside
            className="glass harbor-drawer-in h-full w-68 max-w-[82vw] p-4 flex flex-col justify-between overflow-y-auto"
            aria-label="Mobile Navigation"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 mb-2 border-b border-[var(--border-subtle)]">
              <div className="flex items-center gap-2">
                <span className="skeu-button flex h-8 w-8 items-center justify-center rounded-[10px]" aria-hidden="true">
                  <ChefHat className="h-4 w-4" />
                </span>
                <span className="font-display text-base font-bold" style={{ color: "var(--text)" }}>
                  {t("app.name")}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                aria-label={t("nav.closeMenu")}
                className="neu-raised-sm flex h-9 w-9 items-center justify-center cursor-pointer"
                style={{ color: "var(--text)" }}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1">{renderSidebarContents(false)}</div>
          </aside>
        </div>
      )}
    </div>
  );
}
