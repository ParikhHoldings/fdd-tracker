import { auth, currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import Link from "next/link";
import { BookOpen, Bell, FileSearch, AlertTriangle, Settings, ArrowRight, BarChart3 } from "lucide-react";

export default async function Dashboard() {
  const { userId } = await auth();
  if (!userId) redirect("/auth/sign-in");
  const user = await currentUser();
  const firstName = user?.firstName || "there";

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 flex items-center justify-between h-16">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-indigo-700 rounded-lg flex items-center justify-center"><BookOpen className="w-4 h-4 text-white" /></div>
            <span className="font-bold text-gray-900">FDD Tracker</span>
          </div>
          <nav className="flex items-center gap-5 text-sm">
            <Link href="/watchlist" className="text-gray-600 hover:text-gray-900 flex items-center gap-1"><Bell className="w-4 h-4" />Watchlist</Link>
            <Link href="/franchises" className="text-gray-600 hover:text-gray-900 flex items-center gap-1"><FileSearch className="w-4 h-4" />Franchises</Link>
            <Link href="/profile" className="text-gray-600 hover:text-gray-900"><Settings className="w-4 h-4" /></Link>
          </nav>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Welcome, {firstName}</h1>
          <p className="text-gray-600 mt-1">Your FDD change intelligence feed.</p>
        </div>
        <div className="grid sm:grid-cols-3 gap-6 mb-10">
          {[
            { label: "New Alerts", value: "0", sub: "Today", icon: <Bell className="w-5 h-5 text-indigo-600" /> },
            { label: "FDD Changes", value: "0", sub: "This week", icon: <AlertTriangle className="w-5 h-5 text-red-500" /> },
            { label: "Watching", value: "0", sub: "Franchises", icon: <BarChart3 className="w-5 h-5 text-blue-600" /> },
          ].map((s) => (
            <div key={s.label} className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm">
              <div className="flex items-center justify-between mb-3"><span className="text-sm text-gray-500">{s.label}</span>{s.icon}</div>
              <div className="text-3xl font-bold text-gray-900">{s.value}</div>
              <div className="text-xs text-gray-400 mt-1">{s.sub}</div>
            </div>
          ))}
        </div>
        <div className="bg-indigo-700 rounded-2xl p-8">
          <div className="flex flex-col md:flex-row items-center gap-6">
            <div className="flex-1">
              <h2 className="text-xl font-bold text-white mb-2">Add franchises to your watchlist</h2>
              <p className="text-indigo-300 text-sm">Search for any of 3,000+ franchises and add them. You&apos;ll be alerted the moment their FDD changes.</p>
            </div>
            <Link href="/franchises" className="shrink-0 inline-flex items-center gap-2 bg-white text-indigo-700 px-6 py-3 rounded-xl font-semibold hover:bg-indigo-50 transition-colors">
              Browse Franchises <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
