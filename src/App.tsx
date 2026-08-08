// src/App.tsx
import { ThemeProvider } from './contexts/ThemeContext';
import { NotificationProvider } from './contexts/NotificationContext';
import { LogProvider } from './contexts/LogContext';
import AppRouter from './app/AppRouter';

function App() {
  return (
    <ThemeProvider>
      <NotificationProvider>
        <LogProvider>
          <AppRouter />
        </LogProvider>
      </NotificationProvider>
    </ThemeProvider>
  );
}

export default App;
