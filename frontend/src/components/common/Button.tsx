import { ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'secondary' | 'danger';

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
};

const VARIANT_CLASS: Record<Variant, string> = {
  primary: '',
  secondary: 'secondary-button',
  danger: 'danger-button',
};

export default function Button({ variant = 'primary', className, type, ...rest }: Props) {
  const classes = [VARIANT_CLASS[variant], className].filter(Boolean).join(' ');
  return <button type={type ?? 'button'} className={classes || undefined} {...rest} />;
}
