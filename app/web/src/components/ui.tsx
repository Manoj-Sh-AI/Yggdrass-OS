"use client";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowLeft,
  ArrowUp,
  ArrowDown,
  Bold,
  Italic,
  Underline,
  Strikethrough,
  Code,
  Undo2,
  Redo2,
  Copy,
  Save,
  Download,
  Trash2,
  HardDrive,
  PanelLeft,
  PanelRight,
  Folder,
  FlaskConical,
  Orbit,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  BookmarkPlus,
  Brain,
  BriefcaseBusiness,
  Building2,
  Calendar,
  CalendarClock,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  CornerDownRight,
  Ellipsis,
  File,
  FileClock,
  FileText,
  FolderKanban,
  GraduationCap,
  Heart,
  History,
  House,
  Languages,
  Layers,
  Lightbulb,
  Link2,
  List,
  LoaderCircle,
  LocateFixed,
  MapPin,
  Menu,
  MessageCircle,
  Minus,
  Moon,
  MousePointer2,
  Network,
  NotebookPen,
  Paperclip,
  PartyPopper,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Scan,
  Search,
  Settings2,
  Sparkles,
  Sprout,
  SquareCheck,
  Sun,
  Users,
  X,
  CloudRain,
  type LucideIcon,
} from "lucide-react";
import { useId, useRef, type CSSProperties, type ReactNode } from "react";
import { areaOf } from "@/lib/data";
const icons: Record<string, LucideIcon> = {
  ArrowUp,
  ArrowDown,
  Bold,
  Italic,
  Underline,
  Strikethrough,
  Code,
  Undo2,
  Redo2,
  Copy,
  Save,
  Download,
  Trash2,
  HardDrive,
  PanelLeft,
  PanelRight,
  Folder,
  FlaskConical,
  Orbit,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  BookmarkPlus,
  Brain,
  BriefcaseBusiness,
  Building2,
  Calendar,
  CalendarClock,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  CornerDownRight,
  Ellipsis,
  File,
  FileClock,
  FileText,
  FolderKanban,
  GraduationCap,
  Heart,
  History,
  House,
  Languages,
  Layers,
  Lightbulb,
  Link2,
  List,
  LoaderCircle,
  LocateFixed,
  MapPin,
  Menu,
  MessageCircle,
  Minus,
  Moon,
  MousePointer2,
  Network,
  NotebookPen,
  Paperclip,
  PartyPopper,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Scan,
  Search,
  Settings2,
  Sparkles,
  Sprout,
  SquareCheck,
  Sun,
  Users,
  X,
  CloudRain,
};
export function Icon({
  name,
  size = 19,
  ...props
}: {
  name: string;
  size?: number;
  className?: string;
  style?: CSSProperties;
}) {
  const Comp = icons[name] || FileText;
  return <Comp size={size} strokeWidth={1.65} aria-hidden="true" {...props} />;
}
export function Panel({
  title,
  action,
  children,
  className = "",
  id,
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={`panel ${className}`}>
      {title && (
        <div className="panel-heading">
          <h2>{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function AreaBadge({
  area,
  small = false,
}: {
  area: string;
  small?: boolean;
}) {
  const a = areaOf(area);
  return (
    <span
      className={`area-badge ${small ? "small" : ""}`}
      style={{ "--accent": a.color } as CSSProperties}
    >
      <Icon name={a.icon} size={small ? 14 : 18} />
      {!small && a.name}
    </span>
  );
}
export function Progress({
  value,
  color,
  label,
}: {
  value: number;
  color: string;
  label: string;
}) {
  return (
    <div
      className="progress"
      role="progressbar"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${value}%`, background: color }} />
    </div>
  );
}
export function Empty({
  icon = "Sprout",
  title,
  detail,
  action,
}: {
  icon?: string;
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <Icon name={icon} size={30} />
      <h3>{title}</h3>
      {detail && <p>{detail}</p>}
      {action}
    </div>
  );
}
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  wide = false,
  sheet = false,
  preventDismiss = false,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  wide?: boolean;
  sheet?: boolean;
  preventDismiss?: boolean;
}) {
  const descriptionId = useId(),
    origin = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {/* Closing must not depend on a CSS animation-end event under load. */}
      {open && (
        <Dialog.Portal>
          <Dialog.Overlay className="modal-overlay" />
          <Dialog.Content
            onEscapeKeyDown={(e) => {
              if (preventDismiss) e.preventDefault();
            }}
            onPointerDownOutside={(e) => {
              if (preventDismiss) e.preventDefault();
            }}
            className={`modal ${wide ? "wide" : ""} ${sheet ? "sheet" : ""}`}
            aria-describedby={description ? descriptionId : undefined}
            onOpenAutoFocus={() => {
              origin.current =
                document.querySelector<HTMLElement>("[data-dialog-origin]") ||
                (document.activeElement as HTMLElement);
            }}
            onCloseAutoFocus={(e) => {
              const previous =
                document.querySelector<HTMLElement>("[data-dialog-origin]") ||
                origin.current;
              if (previous?.isConnected) {
                e.preventDefault();
                previous.focus();
                previous.removeAttribute("data-dialog-origin");
              }
            }}
          >
            <div className="modal-heading">
              <div>
                <Dialog.Title>{title}</Dialog.Title>
                {description && (
                  <Dialog.Description id={descriptionId}>
                    {description}
                  </Dialog.Description>
                )}
              </div>
              <Dialog.Close
                className="icon-button"
                aria-label="Close dialog"
                disabled={preventDismiss}
              >
                <Icon name="X" />
              </Dialog.Close>
            </div>
            {children}
          </Dialog.Content>
        </Dialog.Portal>
      )}
    </Dialog.Root>
  );
}
export function rememberFocus() {
  const el = document.activeElement;
  if (el instanceof HTMLElement) el.setAttribute("data-dialog-origin", "");
}
export function relativeTime(date: string) {
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(date).getTime()) / 60000),
  );
  return minutes < 1
    ? "Just now"
    : minutes < 60
      ? `${minutes} min ago`
      : minutes < 1440
        ? `${Math.floor(minutes / 60)} hours ago`
        : `${Math.floor(minutes / 1440)} days ago`;
}
