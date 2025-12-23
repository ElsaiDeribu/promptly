import { z } from 'zod';
import { cn } from '@/lib/utils';
import { useState } from 'react';
import { paths } from '@/routes/paths';
import { useForm } from 'react-hook-form';
import { GoogleIcon } from '@/assets/icons';
import { useAuthContext } from '@/auth/hooks';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useBoolean } from '@/hooks/use-boolean';
import { RouterLink } from '@/routes/components';
import { PATH_AFTER_LOGIN } from '@/config-global';
import { zodResolver } from '@hookform/resolvers/zod';
import LoadingButton from '@/components/ui/loading-button';
import { useRouter, useSearchParams } from '@/routes/hooks';
import FormProvider from '@/components/hook-form/form-provider';
import { FormItem, FormField, FormLabel, FormControl, FormMessage } from '@/components/ui/form';
import { Card, CardTitle, CardHeader, CardContent, CardDescription } from '@/components/ui/card';
// ----------------------------------------------------------------------

export default function LoginView({ className, ...props }: React.ComponentProps<'div'>) {
  const { login } = useAuthContext();

  const router = useRouter();

  const [errorMsg, setErrorMsg] = useState('');

  const searchParams = useSearchParams();

  const returnTo = searchParams.get('returnTo');

  const password = useBoolean();

  const LoginSchema = z.object({
    email: z.string().min(1, 'Email is required').email('Email must be a valid email address'),
    password: z.string().min(1, 'Password is required'),
  });

  const defaultValues = {
    email: 'demo@boilerplate.app',
    password: 'demo1234',
  };

  const methods = useForm({
    resolver: zodResolver(LoginSchema),
    defaultValues,
  });

  const {
    reset,
    handleSubmit,
    formState: { isSubmitting },
  } = methods;

  const onSubmit = handleSubmit(async (data) => {
    try {
      await login?.(data.email, data.password);

      router.push(returnTo || PATH_AFTER_LOGIN);
    } catch (error) {
      console.error(error);
      reset();
      setErrorMsg(typeof error === 'string' ? error : error.message);
    }
  });

  const renderHead = (
    <CardHeader className="text-center">
      <CardTitle className="text-xl">Welcome back</CardTitle>
      <CardDescription>Login to your Boilerplate account</CardDescription>
    </CardHeader>
  );

  const renderForm = (
    <CardContent>
      <div className="grid gap-6">
        <div className="grid gap-6">
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
                <div className="flex items-center">
                  <FormLabel>Password</FormLabel>
                  <RouterLink
                    href={paths.auth.forgotPassword}
                    className="ml-auto text-sm underline-offset-4 hover:underline"
                  >
                    Forgot your password?
                  </RouterLink>
                </div>
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
              Login with Google
            </Button>
          </div>

          <LoadingButton type="submit" className="w-full" loading={isSubmitting}>
            Login
          </LoadingButton>
        </div>
      </div>
    </CardContent>
  );

  const renderFooter = (
    <div className="text-center text-sm">
      Don&apos;t have an account?{' '}
      <RouterLink href={paths.auth.register} className="underline underline-offset-4">
        Sign up
      </RouterLink>
    </div>
  );

  return (
    <div className={cn('flex flex-col gap-6', className)} {...props}>
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
