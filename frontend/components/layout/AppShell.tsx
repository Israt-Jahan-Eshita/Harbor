"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Award,
  BookOpen,
  ChefHat,
  Cpu,
  Home,
  Languages,
  Menu as MenuIcon,
  Mic,
  Moon,
  Package,
  Palette,
  Pill,
  Settings,
  ShoppingBasket,
  Sun,
  Users,
  Utensils,
} from "lucide-react";
import { Sheet } from "@/components/ui/Sheet";
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

const PRIMARY_NAV: NavItem[] = [
  { href: "/dashboard", labelKey: "nav.dashboard", icon: Home },
  { href: "/menu", labelKey: "nav.menu", icon: Utensils },
  { href: "/log", labelKey: "nav.log", icon: Mic },
  { href: "/stock", labelKey: "nav.stock", icon: Package },
];

const SECONDARY_NAV: NavItem[] = [
  { href: "/members", labelKey: "nav.members", icon: Users },
  { href: "/bazar", labelKey: "nav.bazar", icon: ShoppingBasket },
  { href: "/reminders", labelKey: "nav.reminders", icon: Pill },
  { href: "/engine", labelKey: "nav.engine", icon: Cpu },
  { href: "/eval", labelKey: "nav.eval", icon: Award },
  { href: "/settings", labelKey: "nav.settings", icon: Settings },
  { href: "/how-it-works", labelKey: "nav.howItWorks", icon: BookOpen },
  { href: "/styleguide", labelKey: "nav.styleguide", icon: Palette },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const { locale, toggleLocale, t } = useI18n();
  const { resolvedTheme, toggleTheme } = useTheme();
  const { session } = useSession();
  const [moreOpen, setMoreOpen] = useState(false);

  const isPatientRoute = pathname.startsWith("/patient");
  const isLandingOrWelcome = pathname === "/" || pathname === "/welcome";

  if (isPatientRoute) {
    return <main className="min-h-screen">{children}</main>;
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Glass Top App Bar */}
      <header className="glass sticky top-0 z-40 px-4 py-3">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3">
          <Link
            href={session ? "/dashboard" : "/"}
            className="flex items-center gap-2.5 min-h-[48px]"
          >
            <span
              className="skeu-button flex h-10 w-10 items-center justify-center rounded-[14px]"
              aria-hidden="true"
            >
              <ChefHat className="h-5 w-5" />
            </span>
            <div className="leading-tight">
              <span className="block text-lg font-extrabold" style={{ color: "var(--text)" }}>
                {t("app.name")}
              </span>
              <span className="hidden sm:block text-xs" style={{ color: "var(--text-muted)" }}>
                {session ? session.householdName : t("app.subtitle")}
              </span>
            </div>
          </Link>

          <div className="flex items-center gap-2">
            {/* Full-system EN <-> BN Toggle */}
            <button
              type="button"
              data-testid="lang-toggle"
              onClick={toggleLocale}
              title={t("common.languageLabel")}
              className="neu-raised-sm inline-flex min-h-[48px] items-center gap-1.5 rounded-[14px] px-3 py-2 text-sm font-bold cursor-pointer"
              style={{ color: "var(--text)" }}
            >
              <Languages className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
              <span>{locale === "bn" ? "বাং → EN" : "EN → বাং"}</span>
            </button>

            {/* Light <-> Dark Toggle */}
            <button
              type="button"
              data-testid="theme-toggle"
              onClick={toggleTheme}
              aria-label={t("common.themeLabel")}
              className="neu-raised-sm inline-flex min-h-[48px] min-w-[48px] items-center justify-center rounded-[14px] px-3 py-2 text-sm font-bold cursor-pointer"
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

      <div className="mx-auto flex w-full max-w-6xl flex-1 gap-6 px-4 py-5 pb-28 md:pb-8">
        {/* Desktop Glass Side Navigation */}
        {!isLandingOrWelcome && (
          <aside
            className="hidden md:flex md:w-60 shrink-0 flex-col gap-1.5 glass rounded-[24px] p-3 self-start sticky top-24"
            aria-label="Primary Navigation"
          >
            {[...PRIMARY_NAV, ...SECONDARY_NAV].map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex min-h-[48px] items-center gap-3 rounded-[14px] px-3.5 py-2.5 text-sm font-bold transition-all ${
                    active ? "skeu-button" : "hover:bg-[var(--surface)]"
                  }`}
                  style={active ? undefined : { color: "var(--text)" }}
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{t(item.labelKey)}</span>
                </Link>
              );
            })}
          </aside>
        )}

        <main className="min-w-0 flex-1">{children}</main>
      </div>

      {/* Mobile Glass Bottom Navigation */}
      {!isLandingOrWelcome && (
        <nav
          className="glass fixed bottom-0 left-0 right-0 z-40 md:hidden px-2 py-1.5"
          aria-label="Mobile Navigation"
        >
          <div className="mx-auto grid max-w-lg grid-cols-5 gap-1">
            {PRIMARY_NAV.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex min-h-[52px] flex-col items-center justify-center gap-0.5 rounded-[14px] px-1 py-1 text-[11px] font-bold ${
                    active ? "skeu-button" : ""
                  }`}
                  style={active ? undefined : { color: "var(--text)" }}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  <span className="truncate max-w-full">{t(item.labelKey)}</span>
                </Link>
              );
            })}
            <button
              type="button"
              onClick={() => setMoreOpen(true)}
              className="flex min-h-[52px] flex-col items-center justify-center gap-0.5 rounded-[14px] px-1 py-1 text-[11px] font-bold cursor-pointer"
              style={{ color: "var(--text)" }}
            >
              <MenuIcon className="h-4 w-4" aria-hidden="true" />
              <span>{t("common.more")}</span>
            </button>
          </div>
        </nav>
      )}

      {/* More Sheet for Mobile */}
      <Sheet open={moreOpen} onClose={() => setMoreOpen(false)} title={t("common.more")}>
        <div className="grid grid-cols-2 gap-3">
          {SECONDARY_NAV.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMoreOpen(false)}
                className="neu-raised-sm flex min-h-[56px] items-center gap-2.5 px-3.5 py-3 text-sm font-bold"
                style={{ color: "var(--text)" }}
              >
                <Icon className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
                <span>{t(item.labelKey)}</span>
              </Link>
            );
          })}
          <Link
            href="/welcome"
            onClick={() => setMoreOpen(false)}
            className="neu-raised-sm flex min-h-[56px] items-center gap-2.5 px-3.5 py-3 text-sm font-bold"
            style={{ color: "var(--text)" }}
          >
            <Activity className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
            <span>{t("nav.welcome")}</span>
          </Link>
        </div>
      </Sheet>
    </div>
  );
}

