import { Alert, Tabs } from '@mantine/core'
import { useSearchParams } from 'react-router'

import { useAuth } from '../../auth/context'
import { PageHeader } from '../../components/ui'
import { AccountsTab, CategoriesTab } from './AccountsTabs'
import { AddressesTab, BusinessTab, NumberingTab } from './BusinessTabs'
import { TaxTab } from './TaxTab'
import { UsersTab } from './UsersTab'

export function SettingsPage() {
  const { isOwner } = useAuth()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'business'
  return (
    <>
      <PageHeader title="Settings" subtitle="How the business is set up" />
      {!isOwner && (
        <Alert variant="light" mb="md">
          Only the owner can change settings; you can look.
        </Alert>
      )}
      <Tabs value={tab} onChange={(t) => setParams({ tab: t ?? 'business' }, { replace: true })} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="business">Business</Tabs.Tab>
          <Tabs.Tab value="addresses">Addresses</Tabs.Tab>
          <Tabs.Tab value="tax">Sales tax</Tabs.Tab>
          <Tabs.Tab value="accounts">Accounts</Tabs.Tab>
          <Tabs.Tab value="categories">Categories</Tabs.Tab>
          <Tabs.Tab value="numbering">Numbering</Tabs.Tab>
          {isOwner && <Tabs.Tab value="users">Users</Tabs.Tab>}
        </Tabs.List>
        <Tabs.Panel value="business">
          <BusinessTab />
        </Tabs.Panel>
        <Tabs.Panel value="addresses">
          <AddressesTab />
        </Tabs.Panel>
        <Tabs.Panel value="tax">
          <TaxTab />
        </Tabs.Panel>
        <Tabs.Panel value="accounts">
          <AccountsTab />
        </Tabs.Panel>
        <Tabs.Panel value="categories">
          <CategoriesTab />
        </Tabs.Panel>
        <Tabs.Panel value="numbering">
          <NumberingTab />
        </Tabs.Panel>
        {isOwner && (
          <Tabs.Panel value="users">
            <UsersTab />
          </Tabs.Panel>
        )}
      </Tabs>
    </>
  )
}
