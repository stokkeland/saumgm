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

import { Alert, Anchor, Card, Loader, Table, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import { api, unwrap } from '../../api/client'
import { useAuth } from '../../auth/context'
import { PageHeader } from '../../components/ui'
import { UsersTab } from './UsersTab'

/** Old addresses (bookmarks) keep working. */
export function MovedTo({ to }: { to: string }) {
  const { search } = useLocation()
  return <Navigate to={to + search} replace />
}

export function OwnerOnly({ children }: { children: ReactNode }) {
  const { isOwner } = useAuth()
  return isOwner ? children : <Alert variant="light">Only the owner can open this page.</Alert>
}

export function UsersPage() {
  return (
    <>
      <PageHeader title="Users" subtitle="Who can sign in, and their role" />
      <UsersTab />
    </>
  )
}

export function AboutPage() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: async () => unwrap(await api.GET('/api/health')),
  })
  const h = health.data
  const rows: [string, ReactNode][] = h
    ? [
        ['SauMGM (server)', h.version],
        ['SauMGM (this page)', __APP_VERSION__],
        ['Database server', h.database_version ?? '—'],
        [
          'Database version',
          <>
            {h.schema_revision ?? '—'}{' '}
            {h.schema_current === false && (
              <Text span c="red" size="sm">
                (not the newest: the database migrations still have to run)
              </Text>
            )}
          </>,
        ],
      ]
    : []
  return (
    <>
      <PageHeader title="About" subtitle="Versions of this installation" />
      <Card withBorder maw={640}>
        {health.isPending ? (
          <Loader size="sm" />
        ) : (
          <Table>
            <Table.Tbody>
              {rows.map(([label, value]) => (
                <Table.Tr key={label}>
                  <Table.Td c="dimmed" w={200}>
                    {label}
                  </Table.Td>
                  <Table.Td>{value}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
        <Text size="sm" c="dimmed" mt="md">
          SauMGM is free software under the GNU General Public License, version 3 or later.{' '}
          <Anchor href="https://www.saumgm.com/" target="_blank" rel="noreferrer" size="sm">
            www.saumgm.com
          </Anchor>
        </Text>
      </Card>
    </>
  )
}
