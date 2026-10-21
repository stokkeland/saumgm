import '@mantine/core/styles.css'
import '@mantine/dates/styles.css'
import '@mantine/notifications/styles.css'

import { createTheme, MantineProvider } from '@mantine/core'
import { DatesProvider } from '@mantine/dates'
import { ModalsProvider } from '@mantine/modals'
import { Notifications } from '@mantine/notifications'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App.tsx'

const theme = createTheme({
  primaryColor: 'blue',
  defaultRadius: 'sm',
})

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <DatesProvider settings={{ firstDayOfWeek: 0 }}>
        <Notifications position="top-right" />
        <QueryClientProvider client={queryClient}>
          <ModalsProvider>
            <App />
          </ModalsProvider>
        </QueryClientProvider>
      </DatesProvider>
    </MantineProvider>
  </StrictMode>,
)
