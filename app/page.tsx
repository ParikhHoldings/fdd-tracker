import Link from "next/link";
import { CheckCircle, Bell, FileSearch, TrendingDown, AlertTriangle, ArrowRight, BookOpen, BarChart3 } from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen bg-white">
      <nav className="border-b border-gray-100 bg-white sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 flex items-center justify-between h-16">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-indigo-700 rounded-lg flex items-center justify-center">
              <BookOpen className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-gray-900 text-lg">FDD Tracker</span>
          </div>
          <div className="hidden md:flex items-center gap-6">
            <Link href="#features" className="text-gray-600 hover:text-gray-900 text-sm">Features</Link>
            <Link href="#pricing" className="text-gray-600 hover:text-gray-900 text-sm">Pricing</Link>
            <Link href="/auth/sign-in" className="text-gray-600 hover:text-gray-900 text-sm">Sign In</Link>
            <Link href="/auth/sign-up" className="bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-800">Start Free Trial</Link>
          </div>
        </div>
      </nav>

      <section className="py-24 px-4 bg-gradient-to-br from-indigo-50 to-white">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-indigo-100 text-indigo-700 px-3 py-1 rounded-full text-sm font-medium mb-6">
            <AlertTriangle className="w-4 h-4" />
            Franchise Disclosure Document monitoring for brokers & buyers
          </div>
          <h1 className="text-5xl sm:text-6xl font-bold text-gray-900 mb-6 text-balance">
            Know when FDDs change<br /><span className="text-indigo-700">before your clients do</span>
          </h1>
          <p className="text-xl text-gray-600 mb-10 max-w-2xl mx-auto">
            FDD Tracker monitors franchise disclosure documents and alerts you the moment fees change, litigation is added, or unit counts shift. AI summarizes every change in plain English — no 300-page PDF required.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/auth/sign-up" className="bg-indigo-700 text-white px-8 py-4 rounded-xl text-lg font-semibold hover:bg-indigo-800 transition-colors flex items-center gap-2 justify-center">
              Start 14-Day Free Trial <ArrowRight className="w-5 h-5" />
            </Link>
            <Link href="#pricing" className="border-2 border-gray-200 text-gray-700 px-8 py-4 rounded-xl text-lg font-semibold hover:border-gray-300 hover:bg-gray-50 transition-colors">
              See Pricing
            </Link>
          </div>
          <p className="text-sm text-gray-500 mt-4">No credit card · Cancel anytime</p>
        </div>
      </section>

      <section className="py-16 px-4 bg-gray-50">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-2xl font-bold text-gray-900 text-center mb-10">The problem brokers know too well</h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              "Client asks about royalty rates. You quote 6%. Franchise raised it to 8% six months ago.",
              "Franchise added three new lawsuits to Item 3. You didn't know until a buyer's attorney found it.",
              "Unit count dropped 12% this year. You're still presenting it as a growth opportunity.",
              "Item 19 financials changed materially. You're still quoting last year's numbers.",
              "Franchisor quietly raised initial fee by $20K. Your pro forma is now wrong.",
              "You represent 150 brands. Manually checking FDD updates is impossible.",
            ].map((p, i) => (
              <div key={i} className="bg-white rounded-xl p-4 border border-indigo-100 flex items-start gap-3">
                <span className="text-indigo-400 shrink-0">😓</span>
                <p className="text-gray-700 text-sm">{p}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="features" className="py-20 px-4">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">Your FDD intelligence layer</h2>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              { icon: <Bell className="w-6 h-6 text-indigo-700" />, title: "Instant FDD Alerts", desc: "Alerts fired the moment a new FDD is filed with the FTC or state portals. Be the first to know." },
              { icon: <FileSearch className="w-6 h-6 text-indigo-700" />, title: "AI Change Summaries", desc: 'Plain-English summaries of every change. "Royalty up 2%. Initial fee unchanged. 3 new lawsuits in Item 3." No PDF reading.' },
              { icon: <TrendingDown className="w-6 h-6 text-indigo-700" />, title: "Unit Count Trends", desc: "Track unit openings and closures year-over-year. A shrinking system is a red flag — catch it early." },
              { icon: <BarChart3 className="w-6 h-6 text-indigo-700" />, title: "Change History", desc: "5-year history of fee changes, litigation additions, and unit count moves for any franchise. Spot patterns." },
              { icon: <AlertTriangle className="w-6 h-6 text-indigo-700" />, title: "Material Change Flags", desc: "Auto-flag high-severity changes: new lawsuits, fee increases >10%, unit decline >15%, system-wide changes." },
              { icon: <BookOpen className="w-6 h-6 text-indigo-700" />, title: "Franchise Database", desc: "Searchable database of 3,000+ franchises with current FDD data, unit counts, fee structures, and Item 19 availability." },
            ].map((f) => (
              <div key={f.title} className="p-6 border border-gray-100 rounded-xl hover:shadow-sm transition-shadow">
                <div className="mb-4">{f.icon}</div>
                <h3 className="font-semibold text-gray-900 mb-2">{f.title}</h3>
                <p className="text-gray-600 text-sm">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="pricing" className="py-20 px-4 bg-gray-50">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">Pricing</h2>
          <p className="text-gray-600 mb-12">One prevented embarrassment in front of a client pays for a year.</p>
          <div className="grid md:grid-cols-3 gap-6">
            {[
              { name: "Buyer", price: "$29", period: "per month", features: ["50 franchise watchlist", "Email alerts on changes", "AI change summaries", "Current FDD data", "2-year history"], cta: "Start Free Trial", hi: false },
              { name: "Broker", price: "$99", period: "per month", features: ["Unlimited watchlist", "Real-time alerts", "Full change history (5yr)", "Unit count trends", "Material change flags", "Franchise database search", "Up to 3 users"], cta: "Start Free Trial", hi: true },
              { name: "Agency", price: "$249", period: "per month", features: ["Everything in Broker", "Unlimited users", "API access", "Custom alert rules", "Bulk franchise import", "Dedicated onboarding"], cta: "Contact Sales", hi: false },
            ].map((plan) => (
              <div key={plan.name} className={`p-8 rounded-2xl border ${plan.hi ? "border-indigo-600 bg-indigo-700 shadow-lg scale-105" : "border-gray-200 bg-white"}`}>
                <div className={`text-sm font-semibold mb-2 ${plan.hi ? "text-indigo-300" : "text-gray-500"}`}>{plan.name}</div>
                <div className={`text-4xl font-bold mb-1 ${plan.hi ? "text-white" : "text-gray-900"}`}>{plan.price}</div>
                <div className={`text-sm mb-6 ${plan.hi ? "text-indigo-300" : "text-gray-500"}`}>{plan.period}</div>
                <ul className="space-y-3 mb-8 text-left">
                  {plan.features.map((f, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <CheckCircle className={`w-4 h-4 shrink-0 mt-0.5 ${plan.hi ? "text-indigo-300" : "text-green-500"}`} />
                      <span className={`text-sm ${plan.hi ? "text-indigo-100" : "text-gray-600"}`}>{f}</span>
                    </li>
                  ))}
                </ul>
                <Link href="/auth/sign-up" className={`block text-center py-3 rounded-xl font-semibold ${plan.hi ? "bg-white text-indigo-700 hover:bg-indigo-50" : "bg-gray-900 text-white hover:bg-gray-800"}`}>{plan.cta}</Link>
              </div>
            ))}
          </div>
          <p className="text-sm text-gray-500 mt-6">14-day free trial · No credit card required</p>
        </div>
      </section>

      <section className="py-16 px-4 bg-indigo-700">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-white mb-3">Stop flying blind on FDD changes</h2>
          <p className="text-indigo-300 mb-8">14-day free trial. Takes 5 minutes to add your watchlist.</p>
          <Link href="/auth/sign-up" className="inline-flex items-center gap-2 bg-white text-indigo-700 px-8 py-4 rounded-xl text-lg font-semibold hover:bg-indigo-50 transition-colors">
            Start Free Trial <ArrowRight className="w-5 h-5" />
          </Link>
        </div>
      </section>

      <footer className="bg-gray-900 text-gray-400 py-10 px-4">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-indigo-700 rounded flex items-center justify-center"><BookOpen className="w-3 h-3 text-white" /></div>
            <span className="text-white font-semibold">FDD Tracker</span>
          </div>
          <div className="flex gap-6 text-sm">
            <Link href="#features" className="hover:text-white">Features</Link>
            <Link href="#pricing" className="hover:text-white">Pricing</Link>
            <Link href="/auth/sign-up" className="hover:text-white">Start Free</Link>
          </div>
          <div className="text-sm">© 2026 FDD Tracker. All rights reserved.</div>
        </div>
      </footer>
    </div>
  );
}
