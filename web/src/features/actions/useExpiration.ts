import { useEffect, useState } from "react";
export function useExpiration(expiresAt: string) {
  const expiry = new Date(expiresAt).getTime();
  const [expired, setExpired] = useState(() => expiry <= Date.now());
  useEffect(() => {
    const timer = window.setTimeout(
      () => {
        setExpired(true);
      },
      Math.max(0, expiry - Date.now()),
    );
    return () => {
      window.clearTimeout(timer);
    };
  }, [expiry]);
  return expired;
}
