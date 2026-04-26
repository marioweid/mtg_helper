import NextAuth from "next-auth";
import "next-auth/jwt";
import Google from "next-auth/providers/google";

declare module "next-auth" {
  interface Session {
    idToken?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    idToken?: string;
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [Google],
  session: { strategy: "jwt" },
  callbacks: {
    async jwt({ token, account }) {
      if (account?.id_token) token.idToken = account.id_token;
      return token;
    },
    // The session is exposed to the browser. Keep idToken on the JWT only —
    // the server-side proxy (app/api/[...path]/route.ts) reads it via auth()
    // and forwards as a Bearer token to the backend.
    async session({ session }) {
      return session;
    },
  },
  pages: {
    signIn: "/signin",
  },
});
