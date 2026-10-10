"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api, clearPrivateState } from "@/lib/api";

export function SignOut() {
  const router = useRouter();
  useEffect(() => {
    const expire = () => { clearPrivateState(); router.replace("/login"); };
    window.addEventListener("session-expired", expire);
    return () => window.removeEventListener("session-expired", expire);
  }, [router]);
  return <button onClick={async () => {
    try { await api("/auth/logout", { method: "POST" }); } finally {
      clearPrivateState(); router.replace("/login");
    }
  }}>Sign out</button>;
}
