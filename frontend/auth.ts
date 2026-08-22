import NextAuth from "next-auth";
import type { JWT } from "next-auth/jwt";
import "next-auth/jwt";
import Google from "next-auth/providers/google";

declare module "next-auth" {
  interface Session {
    idToken?: string;
    error?: "RefreshFailed";
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    idToken?: string;
    refreshToken?: string;
    expiresAt?: number;
    error?: "RefreshFailed";
  }
}

const REFRESH_LEEWAY_SECONDS = 60;

async function refreshIdToken(token: JWT): Promise<JWT> {
  if (!token.refreshToken) {
    return { ...token, error: "RefreshFailed" };
  }
  try {
    const res = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: process.env["AUTH_GOOGLE_ID"] ?? "",
        client_secret: process.env["AUTH_GOOGLE_SECRET"] ?? "",
        refresh_token: token.refreshToken,
        grant_type: "refresh_token",
      }),
      cache: "no-store",
    });
    const data = (await res.json()) as {
      id_token?: string;
      expires_in?: number;
      refresh_token?: string;
    };
    if (!res.ok || !data.id_token) {
      return { ...token, error: "RefreshFailed" };
    }
    const next: JWT = {
      ...token,
      idToken: data.id_token,
      expiresAt: Math.floor(Date.now() / 1000) + (data.expires_in ?? 3600),
      refreshToken: data.refresh_token ?? token.refreshToken,
    };
    delete next.error;
    return next;
  } catch {
    return { ...token, error: "RefreshFailed" };
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Google({
      authorization: {
        params: {
          access_type: "offline",
          prompt: "consent",
          scope: "openid email profile",
        },
      },
    }),
  ],
  session: { strategy: "jwt" },
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        if (account.id_token) token.idToken = account.id_token;
        if (account.refresh_token) token.refreshToken = account.refresh_token;
        if (account.expires_at) token.expiresAt = account.expires_at;
        return token;
      }
      if (token.expiresAt && Date.now() / 1000 > token.expiresAt - REFRESH_LEEWAY_SECONDS) {
        return refreshIdToken(token);
      }
      return token;
    },
    async session({ session, token }) {
      if (token.idToken) session.idToken = token.idToken;
      if (token.error) session.error = token.error;
      return session;
    },
  },
  pages: {
    signIn: "/signin",
  },
});
