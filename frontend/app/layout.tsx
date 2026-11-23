import type { Metadata, Viewport } from "next";
import { DM_Sans, Fraunces, Hind_Siliguri, JetBrains_Mono } from "next/font/google";
import { AppShell } from "@/components/layout/AppShell";
import { Providers } from "@/lib/providers";
import "./globals.css";

const hindSiliguri = Hind_Siliguri({
  subsets: ["bengali", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-bn",
  display: "swap",
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-latin",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Harbor — Family Care Manager",
  description:
    "Bangla-first household food safety, shared-pot cooking, and meal-timed medicine reminders.",
  manifest: "/manifest.json",
  icons: {
    icon: "/icons/icon-192.svg",
    apple: "/icons/icon-192.svg",
  },
};

export const viewport: Viewport = {
  themeColor: "#A84925",
};

const THEME_INIT_SCRIPT = `
(function() {
  try {
    var theme = localStorage.getItem('harbor_theme') || 'light';
    var resolved = theme === 'system'
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : theme;
    document.documentElement.dataset.theme = resolved;
    var loc = localStorage.getItem('harbor_locale');
    if (loc === 'en' || loc === 'bn') document.documentElement.lang = loc;
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="bn"
      data-theme="light"
      className={`${hindSiliguri.variable} ${dmSans.variable} ${fraunces.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
