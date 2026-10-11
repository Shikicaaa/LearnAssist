import type { SVGProps } from 'react'

// Tiny stroke icons, so we do not need an icon library for a dozen glyphs.
function Icon({ children, size = 18, ...rest }: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  )
}
type P = SVGProps<SVGSVGElement> & { size?: number }

export const PlusIcon = (p: P) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
)
export const SendIcon = (p: P) => (
  <Icon {...p}>
    <path d="M12 19V5M5 12l7-7 7 7" />
  </Icon>
)
export const StopIcon = (p: P) => (
  <Icon {...p}>
    <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
  </Icon>
)
export const DotsIcon = (p: P) => (
  <Icon {...p}>
    <circle cx="12" cy="5" r="1" fill="currentColor" />
    <circle cx="12" cy="12" r="1" fill="currentColor" />
    <circle cx="12" cy="19" r="1" fill="currentColor" />
  </Icon>
)
export const CloseIcon = (p: P) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
)
export const ChatIcon = (p: P) => (
  <Icon {...p}>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
  </Icon>
)
export const FileIcon = (p: P) => (
  <Icon {...p}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5" />
  </Icon>
)
export const TextIcon = (p: P) => (
  <Icon {...p}>
    <path d="M4 6h16M4 12h16M4 18h10" />
  </Icon>
)
export const UploadIcon = (p: P) => (
  <Icon {...p}>
    <path d="M12 16V4M6 10l6-6 6 6M4 20h16" />
  </Icon>
)
export const SearchIcon = (p: P) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" />
  </Icon>
)
export const SidebarIcon = (p: P) => (
  <Icon {...p}>
    <rect x="3" y="4" width="18" height="16" rx="3" />
    <path d="M9 4v16" />
  </Icon>
)
export const BooksIcon = (p: P) => (
  <Icon {...p}>
    <path d="M5 4h4v16H5zM11 4h4v16h-4zM17 6l3.5 1-4 13-3-.8" />
  </Icon>
)
export const LogoutIcon = (p: P) => (
  <Icon {...p}>
    <path d="M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3M16 8l4 4-4 4M20 12H9" />
  </Icon>
)
export const RetryIcon = (p: P) => (
  <Icon {...p}>
    <path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5" />
  </Icon>
)
export const TrashIcon = (p: P) => (
  <Icon {...p}>
    <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
  </Icon>
)
export const DownloadIcon = (p: P) => (
  <Icon {...p}>
    <path d="M12 4v12M6 12l6 6 6-6M4 20h16" />
  </Icon>
)
export const BoltIcon = (p: P) => (
  <Icon {...p}>
    <path d="M13 3L5 14h6l-1 7 8-11h-6z" />
  </Icon>
)
export const SunIcon = (p: P) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4" />
  </Icon>
)
export const MoonIcon = (p: P) => (
  <Icon {...p}>
    <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />
  </Icon>
)
