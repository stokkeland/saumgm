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

import {
  Alert,
  Anchor,
  Button,
  Card,
  Group,
  Loader,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
} from '@mantine/core'
import { IconDownload } from '@tabler/icons-react'
import { keepPreviousData, useQueries, useQuery } from '@tanstack/react-query'
import { useMemo, type ReactNode } from 'react'
import { Link } from 'react-router'

import { api, unwrap } from '../api/client'
import { useJurisdictions, useOrganization } from '../api/lookups'
import { useAuth } from '../auth/context'
import { DateText, Money, PageHeader } from '../components/ui'
import { formatDate, formatRate, todayIso } from '../lib/format'
import { useUrlState } from '../lib/useUrlState'

// -- periods --------------------------------------------------------------------------------------

function iso(d: Date): string {
  return d.toISOString().slice(0, 10)
}

/** The first and last day of the months [startMonth, startMonth + months) (UTC, month 0-based). */
function span(year: number, startMonth: number, months: number): { from: string; to: string } {
  return {
    from: iso(new Date(Date.UTC(year, startMonth, 1))),
    to: iso(new Date(Date.UTC(year, startMonth + months, 0))),
  }
}

function presets(today: string, fiscalStartMonth: number): { label: string; from: string; to: string }[] {
  const [y, m] = today.split('-').map(Number)
  const month = m - 1
  const quarter = Math.floor(month / 3) * 3
  const fiscal = month >= fiscalStartMonth - 1 ? y : y - 1
  const list = [
    { label: 'This month', ...span(y, month, 1) },
    { label: 'Last month', ...span(y, month - 1, 1) },
    { label: 'This quarter', ...span(y, quarter, 3) },
    { label: 'Last quarter', ...span(y, quarter - 3, 3) },
    { label: 'This year', ...span(y, 0, 12) },
    { label: 'Last year', ...span(y - 1, 0, 12) },
  ]
  if (fiscalStartMonth !== 1) {
    list.push(
      { label: 'This fiscal year', ...span(fiscal, fiscalStartMonth - 1, 12) },
      { label: 'Last fiscal year', ...span(fiscal - 1, fiscalStartMonth - 1, 12) },
    )
  }
  return list
}

function PeriodPicker({
  from,
  to,
  onChange,
  extra,
}: {
  from: string
  to: string
  onChange: (from: string, to: string) => void
  extra?: ReactNode
}) {
  const { data: org } = useOrganization()
  const options = useMemo(() => presets(todayIso(), org?.fiscal_year_start_month ?? 1), [org])
  const current = options.find((p) => p.from === from && p.to === to)
  return (
    <Group align="flex-end" mb="md" wrap="wrap">
      <Select
        label="Period"
        w={180}
        placeholder="Custom"
        data={options.map((p) => p.label)}
        value={current?.label ?? null}
        onChange={(label) => {
          const p = options.find((o) => o.label === label)
          if (p) onChange(p.from, p.to)
        }}
      />
      <TextInput type="date" label="From" value={from} onChange={(e) => onChange(e.currentTarget.value, to)} />
      <TextInput type="date" label="To" value={to} onChange={(e) => onChange(from, e.currentTarget.value)} />
      {extra}
    </Group>
  )
}

/** Sales-tax filing periods of each registration (this year and last), to report one at a time. */
function FilingPeriodPicker({ onChange }: { onChange: (from: string, to: string) => void }) {
  const { data: registrations } = useQuery({
    queryKey: ['tax-registrations'],
    queryFn: async () => unwrap(await api.GET('/api/tax/registrations')),
  })
  const { data: jurisdictions } = useJurisdictions()
  const year = Number(todayIso().slice(0, 4))
  const withPeriods = (registrations ?? []).filter((r) => r.filing_frequency)
  const pairs = withPeriods.flatMap((r) => [year, year - 1].map((y) => ({ r, y })))
  const results = useQueries({
    queries: pairs.map(({ r, y }) => ({
      queryKey: ['tax-periods', r.id, String(y)],
      queryFn: async () =>
        unwrap(await api.GET('/api/tax/periods', { params: { query: { registration_id: r.id, year: y } } })),
    })),
  })
  const today = todayIso()
  const options = pairs.flatMap(({ r }, i) => {
    const name = jurisdictions?.find((j) => j.id === r.jurisdiction_id)?.name ?? ''
    return (results[i]?.data ?? [])
      .filter((p) => p.period_start <= today)
      .map((p) => ({
        value: `${p.period_start}|${p.period_end}`,
        label: `${name} ${p.period_start} – ${p.period_end}${p.filing ? ' (filed)' : ''}`,
      }))
  })
  // newest first, one entry per period even if both years list it
  const unique = [...new Map(options.map((o) => [o.label, o])).values()].sort((a, b) =>
    b.value.localeCompare(a.value),
  )
  if (!unique.length) return null
  return (
    <Select
      label="Filing period"
      w={300}
      placeholder="Choose a period to file"
      data={unique}
      value={null}
      onChange={(value) => {
        if (!value) return
        const [from, to] = value.split('|')
        onChange(from, to)
      }}
    />
  )
}

function CsvButton({ path, query }: { path: string; query: Record<string, string> }) {
  const params = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== ''))
  return (
    <Button component="a" href={`${path}?${params}`} variant="default" leftSection={<IconDownload size={16} />}>
      Download CSV
    </Button>
  )
}

function useReport<T>(key: unknown[], enabled: boolean, load: () => Promise<T>) {
  return useQuery({ queryKey: ['report', ...key], queryFn: load, enabled, placeholderData: keepPreviousData })
}

function Status({ isLoading, error }: { isLoading: boolean; error: Error | null }) {
  if (error) return <Alert color="red">{error.message}</Alert>
  if (isLoading) return <Loader />
  return null
}

const num = { style: { textAlign: 'right' as const } }

// -- reports --------------------------------------------------------------------------------------

type Range = { from: string; to: string }

function SalesReport({ range, group, setGroup }: { range: Range; group: string; setGroup: (g: string) => void }) {
  const query = { date_from: range.from, date_to: range.to, group: group as 'month' | 'client' | 'revenue_category' }
  const { data, isLoading, error } = useReport(['sales', query], true, async () =>
    unwrap(await api.GET('/api/reports/sales', { params: { query } })),
  )
  return (
    <Stack>
      <Group justify="space-between">
        <SegmentedControl
          value={group}
          onChange={setGroup}
          data={[
            { value: 'month', label: 'By month' },
            { value: 'client', label: 'By client' },
            { value: 'revenue_category', label: 'By category' },
          ]}
        />
        <CsvButton path="/api/reports/sales.csv" query={query} />
      </Group>
      <Status isLoading={isLoading} error={error} />
      {data && (
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{group === 'month' ? 'Month' : group === 'client' ? 'Client' : 'Category'}</Table.Th>
              <Table.Th {...num}>{group === 'revenue_category' ? 'Invoices' : 'Documents'}</Table.Th>
              <Table.Th {...num}>Sales</Table.Th>
              {group !== 'revenue_category' && <Table.Th {...num}>Tax</Table.Th>}
              {group !== 'revenue_category' && <Table.Th {...num}>Total</Table.Th>}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.rows.map((r) => (
              <Table.Tr key={r.key}>
                <Table.Td>
                  {group === 'client' ? (
                    <Anchor component={Link} to={`/contacts/${r.key}`}>
                      {r.label}
                    </Anchor>
                  ) : (
                    r.label
                  )}
                </Table.Td>
                <Table.Td {...num}>{r.documents}</Table.Td>
                <Table.Td {...num}>
                  <Money value={r.sales} />
                </Table.Td>
                {group !== 'revenue_category' && (
                  <Table.Td {...num}>
                    <Money value={r.tax} />
                  </Table.Td>
                )}
                {group !== 'revenue_category' && (
                  <Table.Td {...num}>
                    <Money value={r.total} />
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
          <Table.Tfoot>
            <Table.Tr>
              <Table.Th>Total</Table.Th>
              <Table.Th />
              <Table.Th {...num}>
                <Money value={data.sales} strong />
              </Table.Th>
              {group !== 'revenue_category' && (
                <Table.Th {...num}>
                  <Money value={data.tax} strong />
                </Table.Th>
              )}
              {group !== 'revenue_category' && (
                <Table.Th {...num}>
                  <Money value={data.total} strong />
                </Table.Th>
              )}
            </Table.Tr>
          </Table.Tfoot>
        </Table>
      )}
      <Text size="xs" c="dimmed">
        Issued invoices dated in the period, less credit notes. Sales are before tax; written-off invoices
        still count as sales.
      </Text>
    </Stack>
  )
}

function Figure({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <Card withBorder padding="sm">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text size="lg">
        <Money value={value} strong={strong} />
      </Text>
    </Card>
  )
}

function SalesTaxReport({ range, basis, setBasis }: { range: Range; basis: string; setBasis: (b: string) => void }) {
  const { locale } = useAuth()
  const query = {
    date_from: range.from,
    date_to: range.to,
    ...(basis ? { basis: basis as 'accrual' | 'cash' } : {}),
  }
  const { data, isLoading, error } = useReport(['sales-tax', query], true, async () =>
    unwrap(await api.GET('/api/reports/sales-tax', { params: { query } })),
  )
  return (
    <Stack>
      <Group justify="space-between">
        <SegmentedControl
          value={basis || data?.basis || 'accrual'}
          onChange={setBasis}
          data={[
            { value: 'accrual', label: 'By invoice date' },
            { value: 'cash', label: 'By payment date' },
          ]}
        />
        <CsvButton path="/api/reports/sales-tax.csv" query={query} />
      </Group>
      <Status isLoading={isLoading} error={error} />
      {data && (
        <>
          <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }}>
            <Figure label="Gross sales" value={data.gross_sales} />
            <Figure label="Non-taxable sales" value={data.non_taxable_sales} />
            <Figure label="Taxable sales" value={data.taxable_sales} />
            <Figure label="Tax collected" value={data.tax_collected} />
            <Figure label="Bad-debt credit" value={data.bad_debt_tax_credit} />
            <Figure label="Net tax due" value={data.net_tax} strong />
          </SimpleGrid>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Jurisdiction</Table.Th>
                <Table.Th>Tax</Table.Th>
                <Table.Th {...num}>Rate</Table.Th>
                <Table.Th {...num}>Taxable</Table.Th>
                <Table.Th {...num}>Tax amount</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.lines.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={5}>
                    <Text size="sm" c="dimmed">
                      No tax in this period
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
              {data.lines.map((line) => (
                <Table.Tr key={`${line.jurisdiction_id}-${line.name}-${line.rate}`}>
                  <Table.Td>{line.jurisdiction}</Table.Td>
                  <Table.Td>{line.name}</Table.Td>
                  <Table.Td {...num}>{formatRate(line.rate, locale.locale)}</Table.Td>
                  <Table.Td {...num}>
                    <Money value={line.taxable} />
                  </Table.Td>
                  <Table.Td {...num}>
                    <Money value={line.tax} />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </>
      )}
      <Text size="xs" c="dimmed">
        By invoice date: tax on invoices issued in the period, with a credit for the tax part of invoices
        written off in it. By payment date: the share of tax in payments received in the period (for
        imported payments, the tax the old system recorded).
      </Text>
    </Stack>
  )
}

type ExpenseRow = { key: string; label: string; account_type: string | null; entries: number; total: string }

function ExpenseRows({ rows }: { rows: ExpenseRow[] }) {
  return rows.map((r) => (
    <Table.Tr key={r.key}>
      <Table.Td>{r.label}</Table.Td>
      <Table.Td {...num}>{r.entries}</Table.Td>
      <Table.Td {...num}>
        <Money value={r.total} />
      </Table.Td>
    </Table.Tr>
  ))
}

function ExpensesReport({ range, group, setGroup }: { range: Range; group: string; setGroup: (g: string) => void }) {
  const query = { date_from: range.from, date_to: range.to, group: group as 'account' | 'vendor' | 'month' }
  const { data, isLoading, error } = useReport(['expenses', query], true, async () =>
    unwrap(await api.GET('/api/reports/expenses', { params: { query } })),
  )
  return (
    <Stack>
      <Group justify="space-between">
        <SegmentedControl
          value={group}
          onChange={setGroup}
          data={[
            { value: 'account', label: 'By account' },
            { value: 'vendor', label: 'By vendor' },
            { value: 'month', label: 'By month' },
          ]}
        />
        <CsvButton path="/api/reports/expenses.csv" query={query} />
      </Group>
      <Status isLoading={isLoading} error={error} />
      {data && (
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{group === 'account' ? 'Account' : group === 'vendor' ? 'Vendor' : 'Month'}</Table.Th>
              <Table.Th {...num}>Entries</Table.Th>
              <Table.Th {...num}>Total</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            <ExpenseRows rows={data.rows} />
          </Table.Tbody>
          <Table.Tfoot>
            <Table.Tr>
              <Table.Th>Total</Table.Th>
              <Table.Th />
              <Table.Th {...num}>
                <Money value={data.total} strong />
              </Table.Th>
            </Table.Tr>
          </Table.Tfoot>
        </Table>
      )}
    </Stack>
  )
}

function ProfitLossReport({ range }: { range: Range }) {
  const query = { date_from: range.from, date_to: range.to }
  const { data, isLoading, error } = useReport(['profit-loss', query], true, async () =>
    unwrap(await api.GET('/api/reports/profit-loss', { params: { query } })),
  )
  const line = (label: ReactNode, value: string, strong = false) => (
    <Table.Tr>
      <Table.Td fw={strong ? 600 : undefined} colSpan={2}>
        {label}
      </Table.Td>
      <Table.Td {...num}>
        <Money value={value} strong={strong} />
      </Table.Td>
    </Table.Tr>
  )
  return (
    <Stack>
      <Group justify="flex-end">
        <CsvButton path="/api/reports/profit-loss.csv" query={query} />
      </Group>
      <Status isLoading={isLoading} error={error} />
      {data && (
        <Table maw={640}>
          <Table.Tbody>
            {line('Sales', data.sales, true)}
            {data.cost_of_goods.length > 0 && (
              <>
                <ExpenseRows rows={data.cost_of_goods} />
                {line('Cost of goods', data.cost_of_goods_total)}
                {line('Gross profit', data.gross_profit, true)}
              </>
            )}
            <ExpenseRows rows={data.expenses} />
            {Number(data.bad_debts) !== 0 && (
              <Table.Tr>
                <Table.Td>Bad debts (written off)</Table.Td>
                <Table.Td />
                <Table.Td {...num}>
                  <Money value={data.bad_debts} />
                </Table.Td>
              </Table.Tr>
            )}
            {line('Expenses', data.expenses_total)}
            {line('Net profit', data.net_profit, true)}
          </Table.Tbody>
        </Table>
      )}
      <Text size="xs" c="dimmed">
        Sales by invoice date, before tax. Expenses by expense date; accounts of type “cost of goods” are
        subtracted first.
      </Text>
    </Stack>
  )
}

function AgingReport() {
  const { locale } = useAuth()
  const { data, isLoading, error } = useReport(['aging'], true, async () => unwrap(await api.GET('/api/reports/aging')))
  const cells = (r: NonNullable<typeof data>['totals'], strong = false) =>
    (['current', 'days_1_30', 'days_31_60', 'days_61_90', 'days_over_90', 'total'] as const).map((b) => (
      <Table.Td key={b} {...num}>
        {Number(r[b]) !== 0 && <Money value={r[b]} strong={strong || b === 'total'} />}
      </Table.Td>
    ))
  return (
    <Stack>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          What clients owe today{data && ` (${formatDate(data.as_of, locale.locale)})`}, by days past the due
          date.
        </Text>
        <CsvButton path="/api/reports/aging.csv" query={{}} />
      </Group>
      <Status isLoading={isLoading} error={error} />
      {data && (
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Client</Table.Th>
              <Table.Th {...num}>Invoices</Table.Th>
              <Table.Th {...num}>Current</Table.Th>
              <Table.Th {...num}>1–30</Table.Th>
              <Table.Th {...num}>31–60</Table.Th>
              <Table.Th {...num}>61–90</Table.Th>
              <Table.Th {...num}>Over 90</Table.Th>
              <Table.Th {...num}>Total</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.rows.map((r) => (
              <Table.Tr key={r.party_id}>
                <Table.Td>
                  <Anchor component={Link} to={`/contacts/${r.party_id}`}>
                    {r.party_name}
                  </Anchor>
                </Table.Td>
                <Table.Td {...num}>{r.invoices}</Table.Td>
                {cells(r)}
              </Table.Tr>
            ))}
          </Table.Tbody>
          <Table.Tfoot>
            <Table.Tr>
              <Table.Th>Total</Table.Th>
              <Table.Th {...num}>{data.totals.invoices}</Table.Th>
              {cells(data.totals, true)}
            </Table.Tr>
          </Table.Tfoot>
        </Table>
      )}
    </Stack>
  )
}

// -- page -----------------------------------------------------------------------------------------

const DEFAULTS = {
  tab: 'sales',
  from: '',
  to: '',
  sales: 'month',
  expenses: 'account',
  basis: '',
}

export function ReportsPage() {
  // the period defaults to this calendar year
  const defaults = useMemo(() => ({ ...DEFAULTS, ...span(Number(todayIso().slice(0, 4)), 0, 12) }), [])
  const [f, setF] = useUrlState(defaults)
  const range = { from: f.from, to: f.to }
  const setRange = (from: string, to: string) => setF({ from, to })
  const datesValid = !!f.from && !!f.to && f.from <= f.to
  return (
    <>
      <PageHeader
        title="Reports"
        subtitle={
          datesValid && f.tab !== 'aging' ? (
            <>
              <DateText value={f.from} /> – <DateText value={f.to} />
            </>
          ) : undefined
        }
      />
      <Tabs value={f.tab} onChange={(tab) => setF({ tab: tab ?? 'sales' })} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="sales">Sales</Tabs.Tab>
          <Tabs.Tab value="tax">Sales tax</Tabs.Tab>
          <Tabs.Tab value="expenses">Expenses</Tabs.Tab>
          <Tabs.Tab value="pl">Profit &amp; loss</Tabs.Tab>
          <Tabs.Tab value="aging">Receivables aging</Tabs.Tab>
        </Tabs.List>
        {f.tab !== 'aging' && (
          <PeriodPicker
            from={f.from}
            to={f.to}
            onChange={setRange}
            extra={f.tab === 'tax' && <FilingPeriodPicker onChange={setRange} />}
          />
        )}
        {f.tab !== 'aging' && !datesValid ? (
          <Alert color="yellow">Choose a period: the start date must be on or before the end date.</Alert>
        ) : (
          <>
            <Tabs.Panel value="sales">
              <SalesReport range={range} group={f.sales} setGroup={(sales) => setF({ sales })} />
            </Tabs.Panel>
            <Tabs.Panel value="tax">
              <SalesTaxReport range={range} basis={f.basis} setBasis={(basis) => setF({ basis })} />
            </Tabs.Panel>
            <Tabs.Panel value="expenses">
              <ExpensesReport range={range} group={f.expenses} setGroup={(expenses) => setF({ expenses })} />
            </Tabs.Panel>
            <Tabs.Panel value="pl">
              <ProfitLossReport range={range} />
            </Tabs.Panel>
            <Tabs.Panel value="aging">
              <AgingReport />
            </Tabs.Panel>
          </>
        )}
      </Tabs>
    </>
  )
}
