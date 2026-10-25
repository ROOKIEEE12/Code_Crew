import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { IdeShell } from "@/components/ide-shell";
import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "CodeCrew Studio — Multi-Agent AI IDE",
  description: "A multi-agent AI team that plans, tests, codes, debugs and documents software.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased dark`}
      suppressHydrationWarning
    >
      <body
        className="h-full overflow-hidden bg-[#101114] text-[#d7dae2]"
        suppressHydrationWarning
      >
        <Providers>
          <IdeShell>{children}</IdeShell>
        </Providers>
      </body>
    </html>
  );
}
