// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * The `cn` helper every copied component imports, written here.
 *
 * The one file in this directory that is not somebody else's: upstream's
 * registry item is now `export { cn } from "cn";`, and the `cn` package is
 * not one this project takes. See ../README.md, "Local modifications" (2),
 * for why, and its vetting table for `clsx` and `tailwind-merge`. The body is
 * what both assistant-ui and shadcn/ui shipped in this file before the
 * package existed.
 */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
