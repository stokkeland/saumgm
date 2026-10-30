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

/** The banking dialogs: an account, a register entry, a transfer, an entry made an expense. */

import {
  Button,
  Checkbox,
  Group,
  Modal,
  NumberInput,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'

import { api, unwrap } from '../../api/client'
import { bankAccountOptions, useBankAccounts } from '../../api/lookups'
import { useAuth } from '../../auth/context'
import { ContactSelect } from '../../components/ContactSelect'
import { todayIso } from '../../lib/format'
import { BANK_ACCOUNT_KINDS } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'
import { invalidateBanking, isCard, useCategoryOptions, type BankAccount, type BankEntry } from './shared'

export function AccountForm({ account, onClose }: { account?: BankAccount; onClose: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { isOwner } = useAuth()
  const form = useForm({
    initialValues: {
      party_id: account?.party_id ?? null,
      name: account?.name ?? '',
      kind: account?.kind ?? 'checking',
      number_last4: account?.number_last4 ?? '',
      opening_date: account?.opening_date ?? todayIso(),
      opening_balance: account ? Number(account.opening_balance) : (0 as number | ''),
      is_active: account?.is_active ?? true,
      notes: account?.notes ?? '',
    },
    validate: {
      name: (v) => (v.trim() ? null : 'Required'),
      number_last4: (v) => (!v || /^[0-9A-Za-z]{1,4}$/.test(v) ? null : 'Up to 4 digits'),
      opening_date: (v) => (v ? null : 'Required'),
    },
  })
  const v = form.values
  const save = useMutation({
    mutationFn: async () => {
      const body = {
        party_id: v.party_id,
        name: v.name.trim(),
        kind: v.kind as BankAccount['kind'],
        number_last4: v.number_last4.trim() || null,
        opening_date: v.opening_date,
        opening_balance: String(v.opening_balance || 0),
        is_active: v.is_active,
        notes: v.notes.trim() || null,
      }
      return account
        ? unwrap(await api.PATCH('/api/bank-accounts/{account_id}', { params: { path: { account_id: account.id } }, body }))
        : unwrap(await api.POST('/api/bank-accounts', { body }))
    },
    onSuccess: (saved) => {
      invalidateBanking(queryClient)
      notifySaved('Account saved')
      onClose()
      if (!account) navigate(`/banking/${saved.id}`)
    },
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE('/api/bank-accounts/{account_id}', { params: { path: { account_id: account!.id } } })),
    onSuccess: () => {
      invalidateBanking(queryClient)
      notifySaved('Account deleted')
      onClose()
      navigate('/banking')
    },
    onError: notifyError,
  })
  const card = v.kind === 'credit_card'
  return (
    <Modal opened onClose={onClose} title={account ? account.name : 'New bank account'} size="lg">
      <form onSubmit={form.onSubmit(() => save.mutate())}>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label="Name" placeholder="Operating checking, Amex Business…" required {...form.getInputProps('name')} />
            <Select label="Kind" data={BANK_ACCOUNT_KINDS} allowDeselect={false} {...form.getInputProps('kind')} />
            <ContactSelect label="Bank" role="financial" value={v.party_id} onChange={(id) => form.setFieldValue('party_id', id)} />
            <TextInput label="Last 4 digits" description="Only the last digits are kept" maxLength={4} {...form.getInputProps('number_last4')} />
            <TextInput type="date" label="Register starts on" required description="No lines before this day" {...form.getInputProps('opening_date')} />
            <NumberInput
              label="Opening balance"
              description={card ? 'Negative: what was owed on that day' : 'The balance on that day'}
              decimalScale={2}
              {...form.getInputProps('opening_balance')}
            />
          </SimpleGrid>
          <Textarea label="Notes" autosize {...form.getInputProps('notes')} />
          {account && <Checkbox label="Open (untick when the account is closed; it stays for history)" {...form.getInputProps('is_active', { type: 'checkbox' })} />}
          <Group justify="space-between">
            <div>
              {account && isOwner && (
                <Button variant="subtle" color="red" loading={remove.isPending} onClick={() => remove.mutate()}>
                  Delete
                </Button>
              )}
            </div>
            <Group>
              <Button variant="default" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" loading={save.isPending}>
                Save
              </Button>
            </Group>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

/** A free entry or a balance adjustment; a transfer's side can change its date, amount and text. */
export function EntryForm({ account, entry, onClose }: { account: BankAccount; entry?: BankEntry; onClose: () => void }) {
  const queryClient = useQueryClient()
  const categories = useCategoryOptions()
  const [making, setMaking] = useState(false)
  const card = isCard(account)
  const form = useForm({
    initialValues: {
      direction: entry && Number(entry.amount) > 0 ? 'in' : 'out',
      amount: entry ? Math.abs(Number(entry.amount)) : ('' as number | ''),
      entry_date: entry?.entry_date ?? todayIso(),
      payee: entry?.payee ?? '',
      description: entry?.description ?? '',
      reference: entry?.reference ?? '',
      account_id: entry?.account_id ? String(entry.account_id) : null,
      cleared: entry ? entry.status !== 'uncleared' : false,
      adjustment: entry?.kind === 'adjustment',
    },
    validate: {
      amount: (v) => (Number(v) > 0 ? null : 'More than zero'),
      entry_date: (v) => (v ? null : 'Required'),
    },
  })
  const v = form.values
  const signed = String((v.direction === 'in' ? 1 : -1) * Number(v.amount || 0))
  const save = useMutation({
    mutationFn: async () => {
      const common = {
        entry_date: v.entry_date,
        amount: signed,
        payee: v.payee.trim() || null,
        description: v.description.trim() || null,
        reference: v.reference.trim() || null,
        account_id: v.account_id ? Number(v.account_id) : null,
        status: (v.cleared ? 'cleared' : 'uncleared') as 'cleared' | 'uncleared',
      }
      if (entry) {
        const body = entry.kind === 'transfer' ? { ...common, account_id: undefined } : common
        return unwrap(await api.PATCH('/api/bank-entries/{entry_id}', { params: { path: { entry_id: entry.id } }, body }))
      }
      return unwrap(
        await api.POST('/api/bank-accounts/{account_id}/entries', {
          params: { path: { account_id: account.id } },
          body: { ...common, kind: v.adjustment ? 'adjustment' : 'manual' },
        }),
      )
    },
    onSuccess: () => {
      invalidateBanking(queryClient)
      notifySaved('Saved')
      onClose()
    },
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE('/api/bank-entries/{entry_id}', { params: { path: { entry_id: entry!.id } } })),
    onSuccess: () => {
      invalidateBanking(queryClient)
      notifySaved(entry?.kind === 'transfer' ? 'Transfer deleted (both sides)' : 'Deleted')
      onClose()
    },
    onError: notifyError,
  })
  if (making && entry) return <ToExpenseForm entry={entry} onClose={onClose} />
  const locked = entry?.status === 'reconciled'
  const transfer = entry?.kind === 'transfer'
  const title = entry ? (transfer ? 'Transfer' : 'Register entry') : 'New entry'
  return (
    <Modal opened onClose={onClose} title={`${title}: ${account.name}`} size="lg">
      <form onSubmit={form.onSubmit(() => save.mutate())}>
        <Stack>
          {locked && (
            <Text size="sm" c="dimmed">
              This line is reconciled with a statement and cannot change.
            </Text>
          )}
          {transfer && (
            <Text size="sm" c="dimmed">
              The other side ({entry.transfer_account_name}) changes with it.
            </Text>
          )}
          <SegmentedControl
            disabled={locked}
            data={[
              { value: 'out', label: card ? 'Charge' : 'Money out' },
              { value: 'in', label: card ? 'Payment or credit' : 'Money in' },
            ]}
            {...form.getInputProps('direction')}
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput type="date" label="Date" required disabled={locked} {...form.getInputProps('entry_date')} />
            <NumberInput label="Amount" min={0} decimalScale={2} required disabled={locked} {...form.getInputProps('amount')} />
            <TextInput label="Payee" disabled={locked} {...form.getInputProps('payee')} />
            <TextInput label="Reference" placeholder="Check no." disabled={locked} {...form.getInputProps('reference')} />
            {!transfer && (
              <Select label="Category" clearable searchable disabled={locked} data={categories} {...form.getInputProps('account_id')} />
            )}
          </SimpleGrid>
          <TextInput label="Description" disabled={locked} {...form.getInputProps('description')} />
          <Group>
            <Checkbox label="Cleared (seen at the bank)" disabled={locked} {...form.getInputProps('cleared', { type: 'checkbox' })} />
            {!entry && (
              <Checkbox label="Balance adjustment (to match a statement)" {...form.getInputProps('adjustment', { type: 'checkbox' })} />
            )}
          </Group>
          <Group justify="space-between">
            <Group>
              {entry && !locked && (
                <Button variant="subtle" color="red" loading={remove.isPending} onClick={() => remove.mutate()}>
                  Delete
                </Button>
              )}
              {entry && (entry.kind === 'manual' || entry.kind === 'adjustment') && Number(entry.amount) < 0 && (
                <Button variant="light" onClick={() => setMaking(true)}>
                  Make an expense…
                </Button>
              )}
            </Group>
            <Group>
              <Button variant="default" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" loading={save.isPending} disabled={locked}>
                Save
              </Button>
            </Group>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

function ToExpenseForm({ entry, onClose }: { entry: BankEntry; onClose: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const categories = useCategoryOptions()
  const [vendor, setVendor] = useState<number | null>(null)
  const [category, setCategory] = useState<string | null>(entry.account_id ? String(entry.account_id) : null)
  const make = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/bank-entries/{entry_id}/expense', {
          params: { path: { entry_id: entry.id } },
          body: { vendor_party_id: vendor, account_id: category ? Number(category) : null },
        }),
      ),
    onSuccess: (saved) => {
      invalidateBanking(queryClient)
      queryClient.invalidateQueries({ queryKey: ['expenses'] })
      notifySaved('Expense made; the line now follows it')
      onClose()
      if (saved.expense_id) navigate(`/expenses/${saved.expense_id}`)
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title="Make an expense of this line">
      <Stack>
        <Text size="sm">
          Records an expense paid from this account for {entry.payee ?? entry.description ?? 'this line'}, so it counts in
          the expense reports. The line stays, linked to the expense.
        </Text>
        <ContactSelect label="Vendor" role="vendor" value={vendor} onChange={setVendor} />
        <Select label="Expense account" required searchable data={categories} value={category} onChange={setCategory} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!category} loading={make.isPending} onClick={() => make.mutate()}>
            Make expense
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export function TransferForm({ fromId, onClose }: { fromId?: number; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: accounts } = useBankAccounts()
  const options = bankAccountOptions(accounts)
  const form = useForm({
    initialValues: {
      from_account_id: fromId ? String(fromId) : null,
      to_account_id: null as string | null,
      entry_date: todayIso(),
      amount: '' as number | '',
      description: '',
      reference: '',
    },
    validate: {
      from_account_id: (v) => (v ? null : 'Choose'),
      to_account_id: (v, values) => (!v ? 'Choose' : v === values.from_account_id ? 'Choose another account' : null),
      amount: (v) => (Number(v) > 0 ? null : 'More than zero'),
    },
  })
  const v = form.values
  const target = accounts?.find((a) => String(a.id) === v.to_account_id)
  const save = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/bank-transfers', {
          body: {
            from_account_id: Number(v.from_account_id),
            to_account_id: Number(v.to_account_id),
            entry_date: v.entry_date,
            amount: String(v.amount),
            description: v.description.trim() || null,
            reference: v.reference.trim() || null,
          },
        }),
      ),
    onSuccess: () => {
      invalidateBanking(queryClient)
      notifySaved('Transfer recorded in both registers')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title="Transfer between accounts">
      <form onSubmit={form.onSubmit(() => save.mutate())}>
        <Stack>
          <SimpleGrid cols={2}>
            <Select label="From" data={options} {...form.getInputProps('from_account_id')} />
            <Select label="To" data={options} {...form.getInputProps('to_account_id')} />
            <TextInput type="date" label="Date" required {...form.getInputProps('entry_date')} />
            <NumberInput label="Amount" min={0} decimalScale={2} required {...form.getInputProps('amount')} />
          </SimpleGrid>
          {target && isCard(target) && Number(target.balance) < 0 && (
            <Group gap="xs">
              <Text size="sm">Paying the card?</Text>
              <Button size="compact-sm" variant="light" onClick={() => form.setFieldValue('amount', -Number(target.balance))}>
                Pay what is owed ({(-Number(target.balance)).toFixed(2)})
              </Button>
            </Group>
          )}
          <TextInput label="Description" placeholder="Card payment, to savings…" {...form.getInputProps('description')} />
          <TextInput label="Reference" {...form.getInputProps('reference')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Transfer
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
