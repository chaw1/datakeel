import { useEffect, useRef } from "react";

export function useQualityPolling(reload: () => void) {
  const latest = useRef(reload);
  useEffect(() => {
    latest.current = reload;
  }, [reload]);
  useEffect(() => {
    const timer = window.setInterval(() => {
      latest.current();
    }, 5000);
    return () => {
      window.clearInterval(timer);
    };
  }, []);
}
