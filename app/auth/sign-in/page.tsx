import { SignIn } from "@clerk/nextjs";
import { BookOpen } from "lucide-react";
export default function SignInPage() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center py-12 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <div className="w-8 h-8 bg-indigo-700 rounded-lg flex items-center justify-center"><BookOpen className="w-4 h-4 text-white" /></div>
            <span className="font-bold text-gray-900 text-lg">FDD Tracker</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Sign in</h1>
        </div>
        <SignIn />
      </div>
    </div>
  );
}
