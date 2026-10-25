"use client";

import { cva, type VariantProps } from "class-variance-authority";
import Link from "next/link";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

/**
 * Every button in the app, in five roles and three sizes.
 *
 * WHY ONE COMPONENT. There were four: the solid primary here, `ApplyButton`
 * (10px uppercase mono in a translucent box), `DownloadButton` (a smaller
 * version of the same), and a scatter of hand-rolled `<button className=…>`
 * on the presets, the exposure scan, the horizon bar and the error pages. Two
 * cards side by side doing the same thing — "run the event study", "compare
 * with peers" — offered differently styled buttons, so the visual language
 * said they were different kinds of action when they were not.
 *
 * The roles are about what pressing does, not about how loud the designer
 * felt:
 *
 *   primary    the one thing this region exists to do. At most one per view.
 *   secondary  a real action that is not the point of the region: run a
 *              study, apply assumptions, compare.
 *   quiet      a utility: download, copy, open, dismiss.
 *   danger     removes something the reader made. Never colours a finding.
 *   chip       a preset or a filter, toggled rather than pressed.
 *
 * Sizes keep the 24×24 floor the accessibility pass established: `xs` is 32px
 * tall, `sm` 36, `md` 44.
 */
export const buttonVariants = cva(
  [
    "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg",
    "font-medium transition-colors",
    "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
    "focus-visible:ring-offset-2 focus-visible:ring-offset-ink",
    "disabled:cursor-not-allowed disabled:opacity-50",
  ],
  {
    variants: {
      variant: {
        primary: "bg-tech font-semibold text-ink hover:bg-tech/85 disabled:bg-rule disabled:text-faint disabled:opacity-100",
        secondary: "border border-tech/50 bg-tech/10 text-chalk hover:bg-tech/20",
        quiet: "border border-rule text-body hover:border-ruleStrong hover:bg-raised hover:text-chalk",
        danger: "border border-dist/40 text-dist hover:bg-dist/10",
        chip: "border border-rule bg-sunken font-mono text-body hover:border-tech/50 hover:text-chalk aria-pressed:border-tech/60 aria-pressed:bg-tech/10 aria-pressed:text-chalk",
      },
      size: {
        xs: "h-8 px-2.5 text-meta",
        sm: "h-9 px-3.5 text-meta",
        md: "h-11 px-5 text-base",
        icon: "h-9 w-9 text-meta",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonVariants = VariantProps<typeof buttonVariants>;

export const Button = forwardRef<HTMLButtonElement,
  React.ComponentProps<"button"> & ButtonVariants>(function Button(
  { className, variant, size, type = "button", ...props }, ref,
) {
  return (
    <button ref={ref} type={type} {...props}
            className={cn(buttonVariants({ variant, size }), className)} />
  );
});

/** The same look on a link — an in-app route, or a file the browser downloads. */
export function ButtonLink({
  href, className, variant, size, children, download, external, ...rest
}: ButtonVariants & {
  href: string;
  className?: string;
  children: React.ReactNode;
  download?: boolean;
  /** A document outside the app shell, such as the field manual. */
  external?: boolean;
} & Omit<React.ComponentProps<"a">, "href" | "download">) {
  const classes = cn(buttonVariants({ variant, size }), className);
  if (download || external) {
    return <a href={href} download={download || undefined} className={classes} {...rest}>{children}</a>;
  }
  return <Link href={href} className={classes} {...rest}>{children}</Link>;
}
