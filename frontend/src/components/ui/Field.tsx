import { useId, type InputHTMLAttributes } from 'react'
import './ui.css'

export function Field({ label, ...rest }: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <input id={id} className="input" {...rest} />
    </div>
  )
}
