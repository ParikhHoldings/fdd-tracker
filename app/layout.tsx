import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "FDD Tracker — Franchise Disclosure Document Change Alerts",
  description: "Get alerted when franchises update their FDDs. AI-powered change detection. Built for franchise brokers and serious buyers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en"><body className={inter.className}>{children}</body></html>
    </ClerkProvider>
  );
}
