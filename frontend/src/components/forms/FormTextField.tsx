import styles from "@/styles/analytics-flow.module.css";

interface FormTextFieldProps {
  id: string;
  label: string;
  value: string;
  placeholder?: string;
  helperText?: string;
  required?: boolean;
  autoComplete?: string;
  onChange: (nextValue: string) => void;
}

export default function FormTextField({
  id,
  label,
  value,
  placeholder,
  helperText,
  required,
  autoComplete,
  onChange,
}: FormTextFieldProps) {
  return (
    <div className={styles.fieldGroup}>
      <label className={styles.label} htmlFor={id}>
        {label}
      </label>
      <input
        className={styles.input}
        id={id}
        value={value}
        placeholder={placeholder}
        required={required}
        autoComplete={autoComplete}
        onChange={(event) => onChange(event.target.value)}
      />
      {helperText ? <p className={styles.helper}>{helperText}</p> : null}
    </div>
  );
}
