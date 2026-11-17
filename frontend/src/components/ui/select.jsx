import * as React from "react"
import * as SelectPrimitive from "@radix-ui/react-select"
import { Check, ChevronDown, ChevronUp, Search } from "lucide-react"

import { cn } from "@/lib/utils"

const SearchCtx = React.createContext("")
const norm = (s) => String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
const textOf = (n) => (n == null || typeof n === "boolean" ? "" : typeof n === "string" || typeof n === "number" ? String(n)
  : Array.isArray(n) ? n.map(textOf).join(" ") : n.props ? textOf(n.props.children) : "")
const countItems = (n) => React.Children.toArray(n).reduce((s, c) => s + (c?.type?.displayName === "SelectItem" ? 1 : c?.props?.children ? countItems(c.props.children) : 0), 0)
const itemMatch = (c, q) => norm(`${textOf(c.props.children)} ${c.props.value ?? ""}`).includes(q)
export const anyMatch = (n, q, extra = "") => !q || React.Children.toArray(n).some((c) => (c?.type?.displayName === "SelectItem" ? (itemMatch(c, q) || norm(extra).includes(q)) : c?.props?.children ? anyMatch(c.props.children, q, c.props["data-label"] || extra) : false))
const SEARCH_MIN = 5

const firstOption = (el) => el?.closest("[role=listbox]")?.querySelector("[role=option]:not(.hidden):not([data-disabled])")

const SelectSearch = ({ q, setQ }) => {
  const ref = React.useRef(null)
  React.useEffect(() => { setQ(""); const id = setTimeout(() => ref.current?.focus(), 60); return () => clearTimeout(id) }, [setQ])
  const onKeyDown = (e) => {
    if (e.key === "Escape" || e.key === "Tab") return
    e.stopPropagation()
    if (e.key === "ArrowDown" || e.key === "Enter") {
      const o = firstOption(ref.current)
      if (!o) return
      e.preventDefault()
      o.focus()
      if (e.key === "Enter") o.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }))
    }
  }
  return (
    <div className="sticky top-0 z-10 flex items-center gap-2 border-b bg-white px-2 py-1.5">
      <Search className="h-3.5 w-3.5 shrink-0 text-slate-400" />
      <input ref={ref} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca…" data-testid="select-search-input"
        className="h-7 w-full bg-transparent text-sm outline-none placeholder:text-slate-400" onKeyDown={onKeyDown} />
    </div>
  )
}
export { SearchCtx, norm }
const Select = SelectPrimitive.Root

const SelectGroup = SelectPrimitive.Group

const SelectValue = SelectPrimitive.Value

const SelectTrigger = React.forwardRef(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      "flex h-9 w-full items-center justify-between whitespace-nowrap rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm ring-offset-background data-[placeholder]:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 [&>span]:line-clamp-1",
      className
    )}
    {...props}>
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className="h-4 w-4 opacity-50" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
))
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName

const SelectScrollUpButton = React.forwardRef(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollUpButton
    ref={ref}
    className={cn("flex cursor-default items-center justify-center py-1", className)}
    {...props}>
    <ChevronUp className="h-4 w-4" />
  </SelectPrimitive.ScrollUpButton>
))
SelectScrollUpButton.displayName = SelectPrimitive.ScrollUpButton.displayName

const SelectScrollDownButton = React.forwardRef(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollDownButton
    ref={ref}
    className={cn("flex cursor-default items-center justify-center py-1", className)}
    {...props}>
    <ChevronDown className="h-4 w-4" />
  </SelectPrimitive.ScrollDownButton>
))
SelectScrollDownButton.displayName =
  SelectPrimitive.ScrollDownButton.displayName

const SelectContent = React.forwardRef(({ className, children, position = "popper", ...props }, ref) => {
  const [q, setQ] = React.useState("")
  const searchable = countItems(children) >= SEARCH_MIN
  return (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      className={cn(
        "relative z-50 max-h-[--radix-select-content-available-height] min-w-[8rem] overflow-y-auto overflow-x-hidden rounded-md border bg-popover text-popover-foreground shadow-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 origin-[--radix-select-content-transform-origin]",
        position === "popper" &&
          "data-[side=bottom]:translate-y-1 data-[side=left]:-translate-x-1 data-[side=right]:translate-x-1 data-[side=top]:-translate-y-1",
        className
      )}
      position={position}
      {...props}>
      {searchable && <SelectSearch q={q} setQ={setQ} />}
      <SelectScrollUpButton />
      <SelectPrimitive.Viewport
        className={cn("p-1", position === "popper" &&
          "h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)]")}>
        <SearchCtx.Provider value={searchable ? norm(q.trim()) : ""}>{children}</SearchCtx.Provider>
        {searchable && q.trim() && !anyMatch(children, norm(q.trim())) && <div className="px-2 py-3 text-center text-xs text-slate-500" data-testid="select-search-empty">Nessun risultato</div>}
      </SelectPrimitive.Viewport>
      <SelectScrollDownButton />
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
  )
})
SelectContent.displayName = SelectPrimitive.Content.displayName

const SelectLabel = React.forwardRef(({ className, ...props }, ref) => (
  <SelectPrimitive.Label
    ref={ref}
    className={cn("px-2 py-1.5 text-sm font-semibold", className)}
    {...props} />
))
SelectLabel.displayName = SelectPrimitive.Label.displayName

const SelectItem = React.forwardRef(({ className, children, ...props }, ref) => {
  const q = React.useContext(SearchCtx)
  const hide = q && !norm(`${textOf(children)} ${props.value ?? ""}`).includes(q)
  return (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-2 pr-8 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      hide && "hidden",
      className
    )}
    {...props}>
    <span className="absolute right-2 flex h-3.5 w-3.5 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <Check className="h-4 w-4" />
      </SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
  )
})
SelectItem.displayName = "SelectItem"

const SelectSeparator = React.forwardRef(({ className, ...props }, ref) => (
  <SelectPrimitive.Separator
    ref={ref}
    className={cn("-mx-1 my-1 h-px bg-muted", className)}
    {...props} />
))
SelectSeparator.displayName = SelectPrimitive.Separator.displayName

export {
  Select,
  SelectGroup,
  SelectValue,
  SelectTrigger,
  SelectContent,
  SelectLabel,
  SelectItem,
  SelectSeparator,
  SelectScrollUpButton,
  SelectScrollDownButton,
}
