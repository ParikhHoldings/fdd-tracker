import Link from "next/link";
import { BookOpen } from "lucide-react";
export default function Page() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 flex items-center gap-4 h-16">
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-indigo-700 rounded-lg flex items-center justify-center"><BookOpen className="w-4 h-4 text-white" /></div>
            <span className="font-bold text-gray-900">FDD Tracker</span>
          </Link>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-10">
        <h1 className="text-2xl font-bold text-gray-900 mb-6 capitalize">franchises</h1>
        <div className="bg-white rounded-2xl border border-gray-100 p-12 text-center">
          <BookOpen className="w-12 h-12 text-indigo-200 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Coming in Phase 2</h2>
          <p className="text-gray-600 text-sm max-w-sm mx-auto">Building soon.</p>
        </div>
      </main>
    </div>
  );
}
