import type { Metadata } from "next";
import { Yeseva_One } from "next/font/google";
import "./globals.css";

const bropellaMock = Yeseva_One({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-bropella",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Finlytics — Intelligent Wealth Analytics",
  description: "Next-generation financial intelligence platform.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${bropellaMock.variable}`}>
      <body>{children}</body>
    </html>
  );
}
