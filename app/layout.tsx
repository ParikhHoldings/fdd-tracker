import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { isPublishableKey } from "@clerk/shared";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });
const fallbackPublishableKey = "pk_test_Y2xlcmsuaW5zcGlyZWQucHVtYS03NC5sY2wuZGV2JA";
const clerkPublishableKey = isPublishableKey(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)
  ? process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  : fallbackPublishableKey;

export const metadata: Metadata = {
  title: "FDD Tracker — Franchise Disclosure Document Change Alerts",
  description: "Get alerted when franchises update their FDDs. AI-powered change detection. Built for franchise brokers and serious buyers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider publishableKey={clerkPublishableKey}>
      <html lang="en"><body className={inter.className}>{children}</body></html>
    </ClerkProvider>
  );
}
