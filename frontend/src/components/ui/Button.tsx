import type { ButtonHTMLAttributes } from 'react'
import { Link, type LinkProps } from 'react-router-dom'
import './ui.css'

type Variant = 'primary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

function classes(variant: Variant, size: Size, block?: boolean) {
  return ['btn', `btn--${variant}`, size !== 'md' && `btn--${size}`, block && 'btn--block']
    .filter(Boolean)
    .join(' ')
}

interface Common {
  variant?: Variant
  size?: Size
  block?: boolean
}

export function Button({
  variant = 'primary',
  size = 'md',
  block,
  className,
  type = 'button',
  ...rest
}: Common & ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type={type} className={`${classes(variant, size, block)} ${className ?? ''}`} {...rest} />
}

export function ButtonLink({ variant = 'primary', size = 'md', block, ...rest }: Common & LinkProps) {
  return <Link className={classes(variant, size, block)} {...rest} />
}
