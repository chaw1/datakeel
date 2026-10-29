interface Agent {
  userAgent: string;
  userAgentData?: { platform?: string };
}

/** Name the Alt/Option modifier the way the viewer's keyboard labels it. */
export function altKeyName(agent: Agent = globalThis.navigator): string {
  const platform = agent.userAgentData?.platform ?? agent.userAgent;
  return /mac|iphone|ipad|ipod/i.test(platform) ? "⌥" : "Alt";
}
