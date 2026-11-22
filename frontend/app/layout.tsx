import type { Metadata } from "next";
import { Noto_Sans_Bengali, Plus_Jakarta_Sans } from "next/font/google";
import { AppShell } from "@/components/layout/AppShell";
import { Providers } from "@/lib/providers";
import "./globals.css";

const notoSansBengali = Noto_Sans_Bengali({
  subsets: ["bengali", "latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-bn",
  display: "swap",
});

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-latin",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Harbor — Family Care Manager",
  description:
    "Bangla-first household food safety, shared-pot cooking, and meal-timed medicine reminders.",
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
      className={`${notoSansBengali.variable} ${plusJakarta.variable}`}
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

