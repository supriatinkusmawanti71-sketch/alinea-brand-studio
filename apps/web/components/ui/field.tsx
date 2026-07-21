import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

type FieldProps = {
  children: ReactNode;
  hint?: string;
  label: string;
};

export function Field({ children, hint, label }: FieldProps) {
  return (
    <label className="form-field">
      <span>{label}</span>
      {children}
      {hint ? <small>{hint}</small> : null}
    </label>
  );
}

export function TextInput({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`text-input ${className}`} {...props} />;
}

export function TextArea({
  className = "",
  rows = 4,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`text-input text-area ${className}`} rows={rows} {...props} />;
}

export function SelectInput({
  children,
  className = "",
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={`text-input ${className}`} {...props}>
      {children}
    </select>
  );
}

