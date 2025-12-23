import { z } from 'zod';
import { cn } from '@/lib/utils';
import { useState } from 'react';
import { paths } from '@/routes/paths';
import { useForm } from 'react-hook-form';
import { useAuthContext } from '@/auth/hooks';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useBoolean } from '@/hooks/use-boolean';
import { RouterLink } from '@/routes/components';
import { ThemeToggle } from '@/theme/components';
import { PATH_AFTER_LOGIN } from '@/config-global';
import GoogleIcon from '@/assets/icons/google-icon';
import { zodResolver } from '@hookform/resolvers/zod';
import LoadingButton from '@/components/ui/loading-button';
import { useRouter, useSearchParams } from '@/routes/hooks';
import FormProvider from '@/components/hook-form/form-provider';
import { Card, CardTitle, CardHeader, CardContent } from '@/components/ui/card';
import { FormItem, FormField, FormLabel, FormControl, FormMessage } from '@/components/ui/form';

// ----------------------------------------------------------------------

export default function RegisterView({ className, ...props }: React.ComponentProps<'div'>) {
  const { register } = useAuthContext();

  const router = useRouter();

  const [errorMsg, setErrorMsg] = useState('');

  const searchParams = useSearchParams();

  const returnTo = searchParams.get('returnTo');

  const password = useBoolean();

  const RegisterSchema = z.object({
    first_name: z.string().min(1, 'First name is required'),
    last_name: z.string().min(1, 'Last name is required'),
    email: z.string().min(1, 'Email is required').email('Email must be a valid email address'),
    password: z.string().min(1, 'Password is required'),
    confirm_password: z.string().min(1, 'Confirm password is required'),
  });

  const defaultValues = {
    first_name: '',
    last_name: '',
    email: '',
    password: '',
    confirm_password: '',
  };

  const methods = useForm({
    resolver: zodResolver(RegisterSchema),
    defaultValues,
  });

  const {
    reset,
    handleSubmit,
    formState: { isSubmitting },
  } = methods;

  const onSubmit = handleSubmit(async (data) => {
    try {
      await register?.(
        data.email,
        data.password,
        data.confirm_password,
        data.first_name,
        data.last_name
      );

      router.push(returnTo || PATH_AFTER_LOGIN);
    } catch (error) {
      console.error(error);
      reset();
      setErrorMsg(typeof error === 'string' ? error : error.message);
    }
  });

  const renderHead = (
    <CardHeader className="text-center">
      <CardTitle className="text-xl">Get started absolutely free</CardTitle>
    </CardHeader>
  );

  const renderForm = (
    <CardContent>
      <div className="grid gap-6">
        <div className="grid gap-6">
          <div className="grid grid-cols-2 gap-4">
            <FormField
              control={methods.control}
              name="first_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>First name</FormLabel>
                  <FormControl>
                    <Input placeholder="First name" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={methods.control}
              name="last_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Last name</FormLabel>
                  <FormControl>
                    <Input placeholder="Last name" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <FormField
            control={methods.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email</FormLabel>
                <FormControl>
                  <Input placeholder="m@example.com" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={methods.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Password</FormLabel>
                <FormControl>
                  <Input type={password.value ? 'text' : 'password'} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={methods.control}
            name="confirm_password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Confirm Password</FormLabel>
                <FormControl>
                  <Input type="password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <div className="after:border-border relative text-center text-sm after:absolute after:inset-0 after:top-1/2 after:z-0 after:flex after:items-center after:border-t">
            <span className="bg-card text-muted-foreground relative z-10 px-2">
              Or continue with
            </span>
          </div>

          <div className="flex flex-col gap-4">
            <Button variant="outline" className="w-full">
              <GoogleIcon />
              Sign up with Google
            </Button>
          </div>

          <LoadingButton type="submit" className="w-full" loading={isSubmitting}>
            Create account
          </LoadingButton>
        </div>
      </div>
    </CardContent>
  );

  const renderFooter = (
    <div className="text-center text-sm">
      Already have an account?{' '}
      <RouterLink href={paths.auth.login} className="underline underline-offset-4">
        Sign in
      </RouterLink>
    </div>
  );

  return (
    <div className={cn('flex flex-col gap-6', className)} {...props}>
      <ThemeToggle />
      <Card>
        {renderHead}

        <FormProvider methods={methods} onSubmit={onSubmit}>
          {!!errorMsg && <h1 style={{ marginBottom: 3, color: 'red' }}>{errorMsg}</h1>}
          {renderForm}
        </FormProvider>
        {renderFooter}
      </Card>
    </div>
  );
}
