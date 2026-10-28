// Local shadcn/ui-style primitives, composed with Radix and class-variance-authority.
import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import * as SliderPrimitive from '@radix-ui/react-slider'
import * as CheckboxPrimitive from '@radix-ui/react-checkbox'
import { cva, type VariantProps } from 'class-variance-authority'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { Check, AlertCircle, LoaderCircle } from 'lucide-react'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
const buttonVariants = cva('button', {
  variants: {
    variant: {
      default: 'button-primary',
      outline: 'button-outline',
      ghost: 'button-ghost',
      danger: 'button-danger',
    },
    size: { default: '', small: 'button-small' },
  },
  defaultVariants: { variant: 'default', size: 'default' },
})
export function Button({
  className,
  variant,
  size,
  asChild = false,
  type = 'button',
  ...props
}: React.ComponentProps<'button'> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : 'button'
  return (
    <Comp
      type={asChild ? undefined : type}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  )
}
export function Input(props: React.ComponentProps<'input'>) {
  return <input {...props} className={cn('input', props.className)} />
}
export function Textarea(props: React.ComponentProps<'textarea'>) {
  return <textarea {...props} className={cn('input textarea', props.className)} />
}
export function Select(props: React.ComponentProps<'select'>) {
  return <select {...props} className={cn('input select', props.className)} />
}
export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string
  hint?: string
  children: React.ReactNode
  className?: string
}) {
  const id = React.useId()
  const input = React.Children.only(children) as React.ReactElement<{
    id?: string
    'aria-describedby'?: string
  }>
  return (
    <div className={cn('field', className)}>
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      {React.cloneElement(input, { id, 'aria-describedby': hint ? `${id}-hint` : undefined })}
      {hint && (
        <span className="field-hint" id={`${id}-hint`}>
          {hint}
        </span>
      )}
    </div>
  )
}
export function Slider(props: React.ComponentProps<typeof SliderPrimitive.Root>) {
  return (
    <SliderPrimitive.Root {...props} className={cn('slider', props.className)}>
      <SliderPrimitive.Track className="slider-track">
        <SliderPrimitive.Range className="slider-range" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb className="slider-thumb" aria-label={props['aria-label']} />
    </SliderPrimitive.Root>
  )
}
export function Checkbox({
  children,
  checked,
  onCheckedChange,
  id,
}: {
  children: React.ReactNode
  checked: boolean
  onCheckedChange: (value: boolean) => void
  id: string
}) {
  return (
    <div className="checkbox-row">
      <CheckboxPrimitive.Root
        id={id}
        className="checkbox"
        checked={checked}
        onCheckedChange={(value) => onCheckedChange(value === true)}
      >
        <CheckboxPrimitive.Indicator>
          <Check size={13} />
        </CheckboxPrimitive.Indicator>
      </CheckboxPrimitive.Root>
      <label htmlFor={id}>{children}</label>
    </div>
  )
}
export function Notice({
  children,
  error = false,
}: {
  children: React.ReactNode
  error?: boolean
}) {
  return (
    <div className={cn('notice', error && 'notice-error')} role={error ? 'alert' : 'status'}>
      <AlertCircle size={18} />
      <div>{children}</div>
    </div>
  )
}
export function Loading({ label = 'Wczytywanie…' }: { label?: string }) {
  return (
    <div className="loading">
      <LoaderCircle className="spin" size={20} />
      {label}
    </div>
  )
}
