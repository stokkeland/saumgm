/*
 * SauMGM - Sauen Management System: billing, sales tax and bookkeeping for small businesses
 * Copyright (C) 2026 J. Thomas Stokkeland - https://www.saumgm.com/
 *
 * This program is free software: you can redistribute it and/or modify it under the terms of the
 * GNU General Public License as published by the Free Software Foundation, either version 3 of
 * the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
 * without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 * See the GNU General Public License for more details. You should have received a copy of the
 * GNU General Public License along with this program (the LICENSE file); if not, see
 * <https://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

import { Alert, Tabs } from '@mantine/core'
import { Navigate, useSearchParams } from 'react-router'

import { useAuth } from '../../auth/context'
import { PageHeader } from '../../components/ui'
import { AccountsTab, CategoriesTab } from './AccountsTabs'
import { AddressesTab, BusinessTab, NumberingTab } from './BusinessTabs'
import { TaxTab } from './TaxTab'

export function SettingsPage() {
  const { isOwner } = useAuth()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'business'
  // Users moved to their own page under Admin in 2.0.
  if (tab === 'users') return <Navigate to="/admin/users" replace />
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
      </Tabs>
    </>
  )
}
