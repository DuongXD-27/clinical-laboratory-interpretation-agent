import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-[var(--radius-md)] border border-transparent bg-clip-padding text-sm font-semibold whitespace-nowrap transition-[background-color,border-color,color,box-shadow,transform] duration-[140ms] ease-[var(--ease-standard)] outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 active:not-aria-[haspopup]:scale-[.985] motion-reduce:transform-none disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-[var(--brand)] text-white shadow-[var(--shadow-button)] hover:bg-[var(--brand-strong)] hover:shadow-[var(--shadow-button-hover)]",
        primary: "bg-[var(--brand)] text-white shadow-[var(--shadow-button)] hover:bg-[var(--brand-strong)] hover:shadow-[var(--shadow-button-hover)]",
        outline:
          "border border-[var(--border-strong)] bg-[var(--surface)] text-[var(--foreground-secondary)] shadow-[var(--shadow-hairline)] hover:border-[var(--brand-muted)] hover:bg-[var(--surface-subtle)] hover:text-foreground",
        secondary:
          "bg-[var(--surface-subtle)] text-[var(--foreground-secondary)] hover:bg-[var(--border)] hover:text-foreground",
        ghost:
          "hover:bg-[var(--surface-subtle)] hover:text-foreground",
        destructive:
          "border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] text-[var(--status-critical-fg)] hover:bg-[color-mix(in_srgb,var(--status-critical-bg),white_18%)]",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "min-h-11 px-4 py-2",
        xs: "min-h-8 px-2.5 text-xs",
        sm: "min-h-9 px-3",
        md: "min-h-11 px-4 py-2",
        lg: "min-h-12 px-6 text-base",
        icon: "size-11",
        "icon-xs": "size-8",
        "icon-sm": "size-9",
        "icon-lg": "size-12",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
)

function Button({
  className,
  variant = "primary",
  size = "md",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
