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

/** Matching the register with a bank statement, and the statements matched before. */

import { Alert, Button, Checkbox, Group, Modal, NumberInput, ScrollArea, SimpleGrid, Stack, Table, Text, TextInput } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, unwrap } from '../../api/client'
import { useAuth } from '../../auth/context'
import { DateText, Money } from '../../components/ui'
import { formatDateTime } from '../../lib/format'
import { notifyError, notifySaved } from '../../lib/notify'
import { invalidateBanking, type BankAccount } from './shared'

const cents = (n: number) => Math.round(n * 100)

export function ReconcileModal({ account, onClose }: { account: BankAccount; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { isOwner, locale } = useAuth()
  const [statementDate, setStatementDate] = useState('')
  const [statementBalance, setStatementBalance] = useState<number | ''>('')
  const [ticked, setTicked] = useState<Set<number> | null>(null)

  const { data: open } = useQuery({
    queryKey: ['bank-entries', account.id, 'open'],
    queryFn: async () => {
      const page = unwrap(
        await api.GET('/api/bank-accounts/{account_id}/entries', {
          params: { path: { account_id: account.id }, query: { limit: 500 } },
        }),
      )
      return page.items.filter((e) => e.status !== 'reconciled').reverse() // oldest first
    },
  })
  const { data: history } = useQuery({
    queryKey: ['bank-reconciliations', account.id],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/bank-accounts/{account_id}/reconciliations', { params: { path: { account_id: account.id } } }),
      ),
  })

  const lines = (open ?? []).filter((e) => !statementDate || e.entry_date <= statementDate)
  // Until the user ticks anything, the lines already marked cleared are ticked.
  const chosen = ticked ?? new Set(lines.filter((e) => e.status === 'cleared').map((e) => e.id))
  const tickedTotal = lines.filter((e) => chosen.has(e.id)).reduce((sum, e) => sum + Number(e.amount), 0)
  const computed = Number(account.reconciled_balance) + tickedTotal
  const difference = statementBalance === '' ? null : cents(Number(statementBalance)) - cents(computed)

  const reconcile = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/bank-accounts/{account_id}/reconciliations', {
          params: { path: { account_id: account.id } },
          body: {
            statement_date: statementDate,
            statement_balance: String(statementBalance),
            entry_ids: lines.filter((e) => chosen.has(e.id)).map((e) => e.id),
          },
        }),
      ),
    onSuccess: (rec) => {
      invalidateBanking(queryClient)
      notifySaved(`Reconciled: ${rec.entries} line(s) match the statement`)
      onClose()
    },
    onError: notifyError,
  })
  const undo = useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.DELETE('/api/bank-reconciliations/{rec_id}', { params: { path: { rec_id: id } } })),
    onSuccess: () => {
      invalidateBanking(queryClient)
      notifySaved('Reconciliation undone; its lines are cleared again')
    },
    onError: notifyError,
  })

  const toggle = (id: number, on: boolean) => {
    const next = new Set(chosen)
    if (on) next.add(id)
    else next.delete(id)
    setTicked(next)
  }

  return (
    <Modal opened onClose={onClose} title={`Reconcile ${account.name}`} size={900}>
      <Stack>
        <Text size="sm">
          Enter the statement's closing date and ending balance, then tick the lines that appear on it. When the difference is
          zero, they become reconciled and locked.
        </Text>
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <TextInput type="date" label="Statement date" required value={statementDate} onChange={(e) => setStatementDate(e.currentTarget.value)} />
          <NumberInput label="Ending balance" decimalScale={2} required value={statementBalance} onChange={(v) => setStatementBalance(v === '' ? '' : Number(v))} />
          <Stack gap={0}>
            <Text size="sm">
              Last reconciled: <Money value={account.reconciled_balance} />{' '}
              {account.last_reconciled_date ? (
                <>
                  (<DateText value={account.last_reconciled_date} />)
                </>
              ) : (
                '(opening balance)'
              )}
            </Text>
            <Text size="sm">
              Ticked lines: <Money value={tickedTotal.toFixed(4)} />
            </Text>
            <Text size="sm" fw={600} c={difference === 0 ? 'green' : difference === null ? undefined : 'red'}>
              Difference: {difference === null ? '—' : <Money value={(difference / 100).toFixed(4)} />}
            </Text>
          </Stack>
        </SimpleGrid>
        <ScrollArea.Autosize mah={360}>
          <Table>
            <Table.Tbody>
              {lines.map((e) => (
                <Table.Tr key={e.id}>
                  <Table.Td w={40}>
                    <Checkbox
                      aria-label={`On the statement: ${e.payee ?? e.description ?? e.id}`}
                      checked={chosen.has(e.id)}
                      onChange={(ev) => toggle(e.id, ev.currentTarget.checked)}
                    />
                  </Table.Td>
                  <Table.Td>
                    <DateText value={e.entry_date} />
                  </Table.Td>
                  <Table.Td>{[e.payee, e.description].filter(Boolean).join(' – ')}</Table.Td>
                  <Table.Td>{e.reference}</Table.Td>
                  <Table.Td ta="right">
                    <Money value={e.amount} />
                  </Table.Td>
                </Table.Tr>
              ))}
              {lines.length === 0 && (
                <Table.Tr>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      No unreconciled lines{statementDate && ' up to that date'}.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </ScrollArea.Autosize>
        {difference !== null && difference !== 0 && (
          <Alert variant="light" color="yellow">
            Not matching yet. Look for a line missing from the register (add it), a typo in an amount, or a line ticked that
            is not on the statement. A small difference not worth tracing can be booked as a balance adjustment.
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!statementDate || difference !== 0} loading={reconcile.isPending} onClick={() => reconcile.mutate()}>
            Reconcile
          </Button>
        </Group>
        {history && history.length > 0 && (
          <Stack gap={4}>
            <Text fw={600} size="sm">
              Statements reconciled
            </Text>
            <Table>
              <Table.Tbody>
                {history.map((r, n) => (
                  <Table.Tr key={r.id}>
                    <Table.Td>
                      <DateText value={r.statement_date} />
                    </Table.Td>
                    <Table.Td ta="right">
                      <Money value={r.statement_balance} />
                    </Table.Td>
                    <Table.Td>{r.entries} line(s)</Table.Td>
                    <Table.Td>
                      <Text size="xs" c="dimmed">
                        {r.created_by ?? 'system'}, {formatDateTime(r.created_at, locale.locale)}
                      </Text>
                    </Table.Td>
                    <Table.Td w={1}>
                      {n === 0 && isOwner && (
                        <Button size="compact-xs" variant="subtle" color="red" loading={undo.isPending} onClick={() => undo.mutate(r.id)}>
                          Undo
                        </Button>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Stack>
        )}
      </Stack>
    </Modal>
  )
}
