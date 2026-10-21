import { Button, Center, Group, Stack, Text, Title } from '@mantine/core'
import { createBrowserRouter, Link, RouterProvider, useRouteError } from 'react-router'

import { RequireAuth } from './auth/RequireAuth'
import { AppLayout } from './components/AppLayout'
import { AccountPage } from './pages/AccountPage'
import { AuditPage } from './pages/AuditPage'
import { CatalogPage } from './pages/CatalogPage'
import { DashboardPage } from './pages/DashboardPage'
import { SettingsPage } from './pages/settings/SettingsPage'
import { SubscriptionsPage } from './pages/SubscriptionsPage'
import { ContactPage } from './pages/contacts/ContactPage'
import { ContactsPage } from './pages/contacts/ContactsPage'
import { InvoicePage, NewInvoicePage } from './pages/invoices/InvoicePage'
import { InvoicesPage } from './pages/invoices/InvoicesPage'
import { DepositPage, DepositsPage, NewDepositPage } from './pages/deposits/DepositPages'
import { ExpensePage, ExpensesPage, NewExpensePage } from './pages/expenses/ExpensePages'
import { ReceivePaymentPage } from './pages/payments/PaymentForm'
import { PaymentPage } from './pages/payments/PaymentPage'
import { PaymentsPage } from './pages/payments/PaymentsPage'
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

/** Shown instead of a blank page if a screen crashes. */
function RouteError() {
  const error = useRouteError()
  return (
    <Center py="xl">
      <Stack align="center" maw={520}>
        <Title order={2}>Something went wrong on this page</Title>
        <Text c="dimmed" ta="center">
          {error instanceof Error ? error.message : String(error)}
        </Text>
        <Group>
          <Button variant="default" onClick={() => window.location.reload()}>
            Reload
          </Button>
          <Button component={Link} to="/">
            Dashboard
          </Button>
        </Group>
      </Stack>
    </Center>
  )
}


const router = createBrowserRouter([
  { path: '/login', element: <LoginPage />, errorElement: <RouteError /> },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    errorElement: <RouteError />,
    children: [
      {
        // A crash inside a page shows the error in place; the menu stays usable.
        errorElement: <RouteError />,
        children: [
          { path: '/', element: <DashboardPage /> },
          { path: '/contacts', element: <ContactsPage /> },
          { path: '/contacts/:id', element: <ContactPage /> },
          { path: '/invoices', element: <InvoicesPage /> },
          { path: '/invoices/new', element: <NewInvoicePage /> },
          { path: '/invoices/:id', element: <InvoicePage /> },
          { path: '/payments', element: <PaymentsPage /> },
          { path: '/payments/new', element: <ReceivePaymentPage /> },
          { path: '/payments/:id', element: <PaymentPage /> },
          { path: '/deposits', element: <DepositsPage /> },
          { path: '/deposits/new', element: <NewDepositPage /> },
          { path: '/deposits/:id', element: <DepositPage /> },
          { path: '/expenses', element: <ExpensesPage /> },
          { path: '/expenses/new', element: <NewExpensePage /> },
          { path: '/expenses/:id', element: <ExpensePage /> },
          { path: '/subscriptions', element: <SubscriptionsPage /> },
          { path: '/catalog', element: <CatalogPage /> },
          { path: '/settings', element: <SettingsPage /> },
          { path: '/audit', element: <AuditPage /> },
          { path: '/account', element: <AccountPage /> },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
