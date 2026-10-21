import type { ReactNode } from 'react'

export type IconName = 'grid' | 'building' | 'bolt' | 'car' | 'wallet' | 'chart' | 'download' | 'chevron' | 'info' | 'clock' | 'trend' | 'leaf' | 'menu' | 'trophy'

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="2" />
        <rect x="14" y="3" width="7" height="7" rx="2" />
        <rect x="3" y="14" width="7" height="7" rx="2" />
        <rect x="14" y="14" width="7" height="7" rx="2" />
      </>
    ),
    building: (
      <>
        <path d="M4 21h16M6 21V6l6-3 6 3v15" />
        <path d="M9 9h1M14 9h1M9 13h1M14 13h1M10 21v-4h4v4" />
      </>
    ),
    bolt: <path d="m13 2-9 12h7l-1 8 9-12h-7z" />,
    car: (
      <>
        <path d="m5 17-2-2v-4l2-1 2-5h10l2 5 2 1v4l-2 2zM5 17v2M19 17v2" />
        <path d="M7 13h.01M17 13h.01M6 10h12" />
      </>
    ),
    wallet: (
      <>
        <path d="M4 5h14a2 2 0 0 1 2 2v12H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h13" />
        <path d="M16 11h6v5h-6a2.5 2.5 0 0 1 0-5z" />
      </>
    ),
    chart: (
      <>
        <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
        <path d="m3 7 6-4 6 5 6-5" />
      </>
    ),
    download: (
      <>
        <path d="M12 3v12m0 0 5-5m-5 5-5-5" />
        <path d="M5 21h14" />
      </>
    ),
    chevron: <path d="m9 18 6-6-6-6" />,
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v6M12 7h.01" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    trend: <path d="m3 17 6-6 4 4 8-9m0 0h-5m5 0v5" />,
    leaf: (
      <>
        <path d="M20 4C11 4 5 8 5 15c0 3 2 5 5 5 7 0 10-8 10-16Z" />
        <path d="M4 21c3-6 7-9 12-12" />
      </>
    ),
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    trophy: (
      <>
        <path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H4v1a4 4 0 0 0 4 4M16 6h4v1a4 4 0 0 1-4 4" />
        <path d="M12 13v4M8 21h8M10 17h4" />
      </>
    ),
  }
  return (
    <svg aria-hidden="true" className="icon" fill="none" height={size} viewBox="0 0 24 24" width={size}>
      {paths[name]}
    </svg>
  )
}
