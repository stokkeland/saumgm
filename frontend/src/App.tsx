import { Button, Center, Stack, Text, Title } from '@mantine/core'
import { createBrowserRouter, Link, RouterProvider } from 'react-router'

import { RequireAuth } from './auth/RequireAuth'
import { AppLayout } from './components/AppLayout'
import { PageHeader } from './components/ui'
import { AccountPage } from './pages/AccountPage'
import { ContactPage } from './pages/contacts/ContactPage'
import { ContactsPage } from './pages/contacts/ContactsPage'
import { LoginPage } from './pages/LoginPage'

function NotFound() {
  return (
    <Center py="xl">
      <Stack align="center">
        <Title order={2}>Page not found</Title>
        <Button component={Link} to="/">
          Back to the dashboard
        </Button>
      </Stack>
    </Center>
  )
}

function Placeholder({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <Text c="dimmed">Coming soon.</Text>
    </>
  )
}

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { path: '/', element: <Placeholder title="Dashboard" /> },
      { path: '/contacts', element: <ContactsPage /> },
      { path: '/contacts/:id', element: <ContactPage /> },
      { path: '/invoices/*', element: <Placeholder title="Invoices" /> },
      { path: '/payments/*', element: <Placeholder title="Payments" /> },
      { path: '/deposits/*', element: <Placeholder title="Deposits" /> },
      { path: '/expenses/*', element: <Placeholder title="Expenses" /> },
      { path: '/subscriptions/*', element: <Placeholder title="Subscriptions" /> },
      { path: '/catalog/*', element: <Placeholder title="Catalog" /> },
      { path: '/settings/*', element: <Placeholder title="Settings" /> },
      { path: '/audit', element: <Placeholder title="Audit log" /> },
      { path: '/account', element: <AccountPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
