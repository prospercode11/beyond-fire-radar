import type { Metadata } from "next";
import { IBM_Plex_Mono, Public_Sans } from "next/font/google";
import "./globals.css";

const publicSans = Public_Sans({
  subsets: ["latin"],
  variable: "--font-public-sans",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-plex-mono",
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Beyond Fire Radar",
  description: "Internal research foundation for Beyond Adjusting",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html className={`${publicSans.variable} ${plexMono.variable}`} lang="en">
      <body>{children}</body>
    </html>
  );
}
