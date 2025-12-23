import type { InputHTMLAttributes } from 'react';

import { forwardRef } from 'react';

// ----------------------------------------------------------------------

export interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  helperText?: string;
  error?: boolean;
  fullWidth?: boolean;
  InputProps?: {
    endAdornment?: React.ReactNode;
    startAdornment?: React.ReactNode;
  };
}

const TextField = forwardRef<HTMLInputElement, TextFieldProps>(
  ({ label, helperText, error, fullWidth, InputProps, ...other }, ref) => (
    <div className={`custom-text-field ${fullWidth ? 'w-full' : ''}`}>
      {label && (
        <label className={`block mb-1 ${error ? 'text-red-500' : 'text-gray-700'}`}>{label}</label>
      )}

      <div className="relative">
        <input
          ref={ref}
          className={`px-3 py-2 border rounded-md w-full ${
            error ? 'border-red-500 focus:ring-red-500' : 'border-gray-300 focus:ring-blue-500'
          } focus:outline-none focus:ring-2`}
          {...other}
        />
        {InputProps?.startAdornment && (
          <div className="absolute inset-y-0 left-0 flex items-center pl-3">
            {InputProps.startAdornment}
          </div>
        )}
        {InputProps?.endAdornment && (
          <div className="absolute inset-y-0 right-0 flex items-center pr-3">
            {InputProps.endAdornment}
          </div>
        )}
      </div>

      {helperText && (
        <p className={`mt-1 text-sm ${error ? 'text-red-500' : 'text-gray-500'}`}>{helperText}</p>
      )}
    </div>
  )
);

export default TextField;
