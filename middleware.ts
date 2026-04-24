import { clerkMiddleware } from "@clerk/nextjs/server";

// Keep Clerk request context available without middleware-level route rewrites.
// Page-level auth handles protected app routes; this prevents staging 404s when
// Clerk blocks middleware protection for non-browser smoke checks.
export default clerkMiddleware();

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
