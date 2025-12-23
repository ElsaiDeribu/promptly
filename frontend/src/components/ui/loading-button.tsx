import * as React from 'react';
import { type VariantProps } from 'class-variance-authority';

import { Button } from './button';

export default function LoadingButton({
  loading,
  children,
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<'button'> &
  VariantProps<typeof Button> & {
    loading?: boolean;
    asChild?: boolean;
  }) {
  return (
    <Button
      disabled={loading}
      className={className}
      variant={variant}
      size={size}
      asChild={asChild}
      {...props}
    >
      {loading ? 'loading...' : children}
    </Button>
  );
}
