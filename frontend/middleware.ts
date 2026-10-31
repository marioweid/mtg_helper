import { auth } from "@/auth";
import { localIdentityEnabled } from "@/lib/local-identity";
import { NextResponse } from "next/server";
import type { NextFetchEvent, NextRequest } from "next/server";

const googleMiddleware = auth((req, _event: NextFetchEvent) => {
  const { pathname } = req.nextUrl;
  const isApiRoute = pathname.startsWith("/api/");
  const isSignInPage = pathname === "/signin";

  if (isApiRoute || isSignInPage) {
    return NextResponse.next();
  }

  if (!req.auth) {
    const url = req.nextUrl.clone();
    url.pathname = "/signin";
    url.searchParams.set("callbackUrl", pathname);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
});

export default function middleware(request: NextRequest, event: NextFetchEvent) {
  if (localIdentityEnabled()) return NextResponse.next();
  return googleMiddleware(request, event);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
