import type { ReactElement } from "react";
import type { ModuleIconName } from "../../types/content";

type IconPaths = () => ReactElement;

const paths: Record<ModuleIconName, IconPaths> = {
  dashboard: () => (
    <>
      <rect x="3" y="13" width="4" height="8" rx="1" />
      <rect x="10" y="8" width="4" height="13" rx="1" />
      <rect x="17" y="4" width="4" height="17" rx="1" />
    </>
  ),
  accounts: () => (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18M8 4v5" />
    </>
  ),
  parsing: () => (
    <>
      <circle cx="6" cy="6" r="2.4" />
      <circle cx="18" cy="6" r="2.4" />
      <circle cx="12" cy="18" r="2.4" />
      <path d="M8 7.5L11 16M16 7.5L13 16" />
    </>
  ),
  broadcast: () => <path d="M3 5l18 7-18 7 4-7-4-7z" strokeLinejoin="round" />,
  invite: () => (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 20c0-3.6 2.7-6 6-6s6 2.4 6 6" strokeLinecap="round" />
      <path d="M18 8v6M15 11h6" strokeLinecap="round" />
    </>
  ),
  phone: () => (
    <path
      d="M9 12l2 2 4-4M21 12c0 4.97-4.03 9-9 9s-9-4.03-9-9 4.03-9 9-9c1.9 0 3.66.59 5.11 1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  shield: () => <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" strokeLinejoin="round" />,
  proxyPool: () => (
    <>
      <circle cx="7" cy="7" r="3" />
      <circle cx="17" cy="7" r="3" />
      <circle cx="12" cy="18" r="3" />
      <path d="M9.5 8.5L14.5 8.5M8.5 9.5L11 15M15.5 9.5L13 15" strokeDasharray="2 2" />
    </>
  ),
  sms: () => (
    <>
      <rect x="4" y="4" width="16" height="12" rx="2" />
      <path d="M8 20l3-4h2l3 4M8 8h8M8 11h5" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  marketplace: () => (
    <>
      <path d="M4 8l1.5-4h13L20 8" strokeLinejoin="round" />
      <path d="M4 8h16v11a1 1 0 01-1 1H5a1 1 0 01-1-1V8z" strokeLinejoin="round" />
      <path d="M9 12a3 3 0 006 0" strokeLinecap="round" />
    </>
  ),
  convert: () => (
    <>
      <path d="M4 8h13M17 8l-3-3M17 8l-3 3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M20 16H7M7 16l3-3M7 16l3 3" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  fingerprint: () => (
    <>
      <path d="M12 3a9 9 0 00-9 9c0 2 .4 3.6 1 5" strokeLinecap="round" />
      <path d="M12 3a9 9 0 019 9c0 1.2-.1 2.2-.4 3.2" strokeLinecap="round" />
      <path d="M7 20c-.8-1.7-1.3-3.6-1.3-6a6.3 6.3 0 0112.6 0c0 .8-.1 1.6-.2 2.3" strokeLinecap="round" />
      <path d="M12 20c-1.3-2-2-4-2-6.3a2.3 2.3 0 014.6 0c0 1.1-.2 2-.5 2.8" strokeLinecap="round" />
    </>
  ),
  shuffle: () => (
    <>
      <path
        d="M3 6h3.5c2 0 3 1 4.5 3.5M3 18h3.5c2 0 3-1 4.5-3.5M14 6h3.5c2 0 3 1 4.5 3.5M14 18h3.5c2 0 3-1 4.5-3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M18 3l3 3-3 3M18 15l3 3-3 3" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  lock: () => (
    <>
      <rect x="4" y="9" width="16" height="11" rx="2" />
      <path d="M8 9V6a4 4 0 018 0v3" />
    </>
  ),
};

export function ModuleIcon({ name }: { name: ModuleIconName }) {
  const Paths = paths[name];
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <Paths />
    </svg>
  );
}
