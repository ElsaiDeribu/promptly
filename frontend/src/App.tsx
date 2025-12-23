import './App.css';

import Router from '@/routes/sections';
import { AuthProvider } from '@/auth/context/auth';
import ThemeProvider from '@/theme/theme-provider';

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Router />
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
