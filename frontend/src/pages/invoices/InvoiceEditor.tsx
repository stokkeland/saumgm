import {
  Accordion,
  ActionIcon,
  Alert,
  Button,
  Card,
  Divider,
  Group,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useDebouncedValue } from '@mantine/hooks'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'

import { api, unwrap, type Schemas } from '../../api/client'
import { jurisdictionOptions, useJurisdictions, useTaxCategories } from '../../api/lookups'
import { useAuth } from '../../auth/context'
import { ContactSelect } from '../../components/ContactSelect'
import { Money } from '../../components/ui'
import { formatRate } from '../../lib/format'
import { notifyError, notifySaved } from '../../lib/notify'

type Invoice = Schemas['InvoiceOut']
type LineIn = Schemas['LineIn']
type Mode = 'create' | 'draft' | 'revise'

interface LineForm {
  key: string
  catalog_item_id: string | null
  subscription_id: number | null
  description: string
  quantity: number | string
  unit: string
  unit_price: number | string
  discount_pct: number | string
  /** The stored per-unit discount; sent unchanged unless the percentage was edited. */
  unit_discount: string | null
  pct_touched: boolean
  tax_category_id: string | null
}

const BILL_TO: [keyof Invoice & string, string][] = [
  ['bill_to_company', 'Company'],
  ['bill_to_name', 'Attention'],
  ['bill_to_line1', 'Address line 1'],
  ['bill_to_line2', 'Address line 2'],
  ['bill_to_city', 'City'],
  ['bill_to_region', 'State / province'],
  ['bill_to_postal_code', 'Postal code'],
  ['bill_to_country', 'Country'],
  ['bill_to_email', 'Email'],
  ['bill_to_phone', 'Phone'],
]

let nextKey = 0
const newKey = () => `line-${++nextKey}`

function blankLine(): LineForm {
  return {
    key: newKey(),
    catalog_item_id: null,
    subscription_id: null,
    description: '',
    quantity: 1,
    unit: '',
    unit_price: '',
    discount_pct: 0,
    unit_discount: null,
    pct_touched: true,
    tax_category_id: null,
  }
}

function fromLine(line: Schemas['LineOut']): LineForm {
  const price = Number(line.unit_price)
  const discount = Number(line.unit_discount)
  return {
    key: newKey(),
    catalog_item_id: line.catalog_item_id ? String(line.catalog_item_id) : null,
    subscription_id: line.subscription_id ?? null,
    description: line.description,
    quantity: Number(line.quantity),
    unit: line.unit ?? '',
    unit_price: price,
    discount_pct: price ? Math.round((discount / price) * 100 * 10000) / 10000 : 0,
    unit_discount: line.unit_discount,
    pct_touched: false,
    tax_category_id: line.tax_category_id ? String(line.tax_category_id) : null,
  }
}

function toLineIn(line: LineForm): LineIn {
  const base = {
    catalog_item_id: line.catalog_item_id ? Number(line.catalog_item_id) : null,
    subscription_id: line.subscription_id,
    description: line.description.trim() || null,
    quantity: String(line.quantity === '' ? 0 : line.quantity),
    unit: line.unit.trim() || null,
    unit_price: line.unit_price === '' ? null : String(line.unit_price),
    tax_category_id: line.tax_category_id ? Number(line.tax_category_id) : null,
  }
  return line.pct_touched || line.unit_discount === null
    ? { ...base, discount_pct: String(line.discount_pct || 0) }
    : { ...base, unit_discount: line.unit_discount }
}

function useCatalogOptions() {
  return useQuery({
    queryKey: ['catalog-options'],
    queryFn: async () =>
      unwrap(await api.GET('/api/catalog', { params: { query: { active: true, limit: 500 } } })).items,
    staleTime: 60_000,
  })
}

export function InvoiceEditor({
  mode,
  invoice,
  partyId,
  onDone,
  onCancel,
}: {
  mode: Mode
  invoice?: Invoice
  partyId?: number | null
  onDone: (invoice: Invoice, issued?: boolean) => void
  onCancel: () => void
}) {
  const { locale } = useAuth()
  const queryClient = useQueryClient()
  const { data: catalog } = useCatalogOptions()
  const { data: categories } = useTaxCategories()
  const { data: jurisdictions } = useJurisdictions()
  const isCredit = invoice?.kind === 'credit_note'

  const form = useForm({
    initialValues: {
      party_id: invoice?.party_id ?? partyId ?? null,
      issue_date: invoice?.issue_date ?? '',
      terms_days: invoice?.terms_days ?? ('' as number | ''),
      terms_text: invoice?.terms_text ?? '',
      tax_jurisdiction_id: invoice?.tax_jurisdiction_id ? String(invoice.tax_jurisdiction_id) : null,
      freight: Number(invoice?.freight ?? 0),
      adjustment: Number(invoice?.adjustment ?? 0),
      adjustment_note: invoice?.adjustment_note ?? '',
      notes: invoice?.notes ?? '',
      reason: '',
      lines: invoice?.lines.length ? invoice.lines.map(fromLine) : [blankLine()],
      ...Object.fromEntries(BILL_TO.map(([key]) => [key, (invoice?.[key] as string | null) ?? ''])),
    } as Record<string, unknown> & {
      party_id: number | null
      issue_date: string
      terms_days: number | ''
      terms_text: string
      tax_jurisdiction_id: string | null
      freight: number
      adjustment: number
      adjustment_note: string
      notes: string
      reason: string
      lines: LineForm[]
    },
    validate: {
      party_id: (v) => (v ? null : 'Choose a client'),
      reason: (v) => (mode === 'revise' && (v as string).trim().length < 3 ? 'Say why the invoice changes' : null),
    },
  })
  const v = form.values

  /** Header fields to send: everything for drafts being saved, but defaults (bill-to, terms,
   * tax location) only when the user changed them, so the server can fill them from the contact. */
  const header = () => {
    const body: Record<string, unknown> = {
      issue_date: v.issue_date || null,
      freight: String(v.freight || 0),
      adjustment: String(v.adjustment || 0),
      adjustment_note: v.adjustment_note.trim() || null,
      notes: v.notes.trim() || null,
    }
    if (form.isDirty('terms_days')) body.terms_days = v.terms_days === '' ? null : v.terms_days
    if (form.isDirty('terms_text')) body.terms_text = v.terms_text.trim() || null
    if (form.isDirty('tax_jurisdiction_id')) {
      body.tax_jurisdiction_id = v.tax_jurisdiction_id ? Number(v.tax_jurisdiction_id) : null
    }
    for (const [key] of BILL_TO) {
      if (form.isDirty(key)) body[key] = (v[key] as string).trim() || null
    }
    return body
  }

  // Live totals and tax from the server, a moment after the user stops typing.
  const calcBody = useMemo(
    () =>
      v.party_id
        ? {
            party_id: v.party_id,
            tax_jurisdiction_id: v.tax_jurisdiction_id ? Number(v.tax_jurisdiction_id) : null,
            issue_date: v.issue_date || null,
            freight: String(v.freight || 0),
            adjustment: String(v.adjustment || 0),
            lines: v.lines
              .filter((l) => l.description.trim() || l.catalog_item_id)
              .map(toLineIn),
          }
        : null,
    [v.party_id, v.tax_jurisdiction_id, v.issue_date, v.freight, v.adjustment, v.lines],
  )
  const [debounced] = useDebouncedValue(calcBody, 400)
  const calc = useQuery({
    queryKey: ['invoice-calc', debounced],
    queryFn: async () => unwrap(await api.POST('/api/invoices/calculate', { body: debounced! })),
    enabled: !!debounced && debounced.lines.length > 0,
    placeholderData: keepPreviousData,
    retry: false,
  })

  const save = useMutation({
    mutationFn: async ({ issue }: { issue: boolean }) => {
      const lines = v.lines.filter((l) => l.description.trim() || l.catalog_item_id).map(toLineIn)
      let saved: Invoice
      if (mode === 'create') {
        saved = unwrap(
          await api.POST('/api/invoices', { body: { ...header(), party_id: v.party_id!, lines } }),
        )
      } else if (mode === 'draft') {
        saved = unwrap(
          await api.PATCH('/api/invoices/{invoice_id}', {
            params: { path: { invoice_id: invoice!.id } },
            body: { ...header(), party_id: v.party_id, lines },
          }),
        )
      } else {
        saved = unwrap(
          await api.POST('/api/invoices/{invoice_id}/revise', {
            params: { path: { invoice_id: invoice!.id } },
            body: { ...header(), reason: v.reason.trim(), lines },
          }),
        )
      }
      if (issue) {
        saved = unwrap(
          await api.POST('/api/invoices/{invoice_id}/issue', {
            params: { path: { invoice_id: saved.id } },
            body: { issue_date: v.issue_date || null },
          }),
        )
      }
      return { saved, issue }
    },
    onSuccess: ({ saved, issue }) => {
      queryClient.setQueryData(['invoice', saved.id], saved)
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['contact-balance'] })
      if (issue) notifySaved(`${isCredit ? 'Credit note' : 'Invoice'} ${saved.number} issued`)
      else notifySaved(mode === 'revise' ? `Revision ${saved.revision_no} saved` : 'Draft saved')
      saved.warnings.forEach((w) => notifyError(new Error(w)))
      onDone(saved, issue)
    },
    onError: notifyError,
  })

  const catalogOptions = (catalog ?? []).map((item) => ({
    value: String(item.id),
    label: item.sku ? `${item.sku} — ${item.name}` : item.name,
  }))
  const categoryOptions = (categories ?? []).map((c) => ({ value: String(c.id), label: c.name }))

  const pickItem = (index: number, id: string | null) => {
    const item = catalog?.find((c) => String(c.id) === id)
    const line = v.lines[index]
    form.setFieldValue(`lines.${index}`, {
      ...line,
      catalog_item_id: id,
      ...(item && {
        description: !line.description || line.catalog_item_id ? item.name : line.description,
        unit_price: Number(item.price),
        unit: item.unit ?? '',
        discount_pct: Number(item.default_discount_pct),
        pct_touched: true,
        tax_category_id: item.tax_category_id ? String(item.tax_category_id) : null,
      }),
    })
  }

  const historical = invoice?.is_historical ?? false
  const result = calc.data

  return (
    <form
      onSubmit={form.onSubmit(() => save.mutate({ issue: false }))}
      onKeyDown={(e) => {
        // Enter in a field should not submit the whole invoice.
        if (e.key === 'Enter' && (e.target as HTMLElement).tagName === 'INPUT') e.preventDefault()
      }}
    >
      <Stack>
        {mode === 'revise' && (
          <Alert color="orange" variant="light" title="Revising an issued invoice">
            The current version is kept in the invoice's revision history. The number stays the same.
          </Alert>
        )}
        <Card withBorder>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }}>
            <ContactSelect
              label="Client"
              role="client"
              required
              disabled={mode === 'revise'}
              value={v.party_id}
              onChange={(id) => form.setFieldValue('party_id', id)}
              error={form.errors.party_id}
              style={{ gridColumn: 'span 2' }}
            />
            <TextInput
              type="date"
              label="Invoice date"
              description={mode === 'revise' ? undefined : 'Empty: the day it is issued'}
              {...form.getInputProps('issue_date')}
            />
            <Select
              label="Sales-tax location"
              placeholder="From the client's address"
              clearable
              searchable
              data={jurisdictionOptions(jurisdictions)}
              {...form.getInputProps('tax_jurisdiction_id')}
            />
            <NumberInput
              label="Terms (days)"
              placeholder="Client / business default"
              min={0}
              allowDecimal={false}
              {...form.getInputProps('terms_days')}
            />
            <TextInput
              label="Terms text"
              placeholder="e.g. Net 30 days"
              style={{ gridColumn: 'span 3' }}
              {...form.getInputProps('terms_text')}
            />
          </SimpleGrid>
          <Accordion variant="contained" mt="md">
            <Accordion.Item value="billto">
              <Accordion.Control>
                <Text size="sm">Bill to {mode === 'create' && '(copied from the client when saved)'}</Text>
              </Accordion.Control>
              <Accordion.Panel>
                <SimpleGrid cols={{ base: 1, sm: 2 }}>
                  {BILL_TO.map(([key, label]) => (
                    <TextInput key={key} label={label} {...form.getInputProps(key)} />
                  ))}
                </SimpleGrid>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
        </Card>

        <Card withBorder p={0}>
          <Table.ScrollContainer minWidth={900}>
            <Table verticalSpacing={6}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={230}>Item</Table.Th>
                  <Table.Th>Description</Table.Th>
                  <Table.Th w={90}>Qty</Table.Th>
                  <Table.Th w={80}>Unit</Table.Th>
                  <Table.Th w={110}>Price</Table.Th>
                  <Table.Th w={90}>Disc. %</Table.Th>
                  <Table.Th w={150}>Tax category</Table.Th>
                  <Table.Th w={110} style={{ textAlign: 'right' }}>
                    Amount
                  </Table.Th>
                  <Table.Th w={40} />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {v.lines.map((line, i) => (
                  <Table.Tr key={line.key}>
                    <Table.Td>
                      <Select
                        aria-label="Catalog item"
                        placeholder="Free text"
                        searchable
                        clearable
                        data={catalogOptions}
                        value={line.catalog_item_id}
                        onChange={(id) => pickItem(i, id)}
                      />
                    </Table.Td>
                    <Table.Td>
                      <TextInput aria-label="Description" {...form.getInputProps(`lines.${i}.description`)} />
                    </Table.Td>
                    <Table.Td>
                      <NumberInput aria-label="Quantity" hideControls decimalScale={4} {...form.getInputProps(`lines.${i}.quantity`)} />
                    </Table.Td>
                    <Table.Td>
                      <TextInput aria-label="Unit" {...form.getInputProps(`lines.${i}.unit`)} />
                    </Table.Td>
                    <Table.Td>
                      <NumberInput aria-label="Unit price" hideControls decimalScale={4} {...form.getInputProps(`lines.${i}.unit_price`)} />
                    </Table.Td>
                    <Table.Td>
                      <NumberInput
                        aria-label="Discount percent"
                        hideControls
                        min={0}
                        max={100}
                        decimalScale={4}
                        value={line.discount_pct}
                        onChange={(pct) => {
                          form.setFieldValue(`lines.${i}.discount_pct`, pct)
                          form.setFieldValue(`lines.${i}.pct_touched`, true)
                        }}
                      />
                    </Table.Td>
                    <Table.Td>
                      <Select
                        aria-label="Tax category"
                        placeholder="Taxable"
                        clearable
                        data={categoryOptions}
                        {...form.getInputProps(`lines.${i}.tax_category_id`)}
                      />
                    </Table.Td>
                    <Table.Td style={{ textAlign: 'right' }}>
                      <Money value={result?.lines[i]?.line_total} />
                    </Table.Td>
                    <Table.Td>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        aria-label="Remove line"
                        onClick={() => form.removeListItem('lines', i)}
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Group p="xs">
            <Button
              variant="subtle"
              size="xs"
              leftSection={<IconPlus size={14} />}
              onClick={() => form.insertListItem('lines', blankLine())}
            >
              Add line
            </Button>
          </Group>
        </Card>

        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <Stack>
            <Textarea label="Notes on the invoice" autosize minRows={2} {...form.getInputProps('notes')} />
            {mode === 'revise' && (
              <Textarea
                label="Reason for this revision"
                required
                autosize
                minRows={2}
                {...form.getInputProps('reason')}
              />
            )}
          </Stack>
          <Card withBorder>
            <Stack gap={6}>
              <Group justify="space-between">
                <Text size="sm">Subtotal</Text>
                <Money value={result?.subtotal} />
              </Group>
              <Group justify="space-between" wrap="nowrap">
                <Text size="sm">Freight</Text>
                <NumberInput aria-label="Freight" w={120} hideControls decimalScale={2} min={0} {...form.getInputProps('freight')} />
              </Group>
              <Group justify="space-between" wrap="nowrap" gap="xs">
                <TextInput
                  aria-label="Adjustment note"
                  placeholder="Adjustment (note)"
                  style={{ flex: 1 }}
                  {...form.getInputProps('adjustment_note')}
                />
                <NumberInput aria-label="Adjustment" w={120} hideControls decimalScale={2} {...form.getInputProps('adjustment')} />
              </Group>
              {historical ? (
                <Group justify="space-between">
                  <Text size="sm">Sales tax (as imported, not recalculated)</Text>
                  <Money value={invoice?.tax_total} />
                </Group>
              ) : (
                result?.taxes.map((t) => (
                  <Group key={`${t.jurisdiction_id}-${t.name}`} justify="space-between">
                    <Text size="sm">
                      {t.name} {formatRate(t.rate, locale.locale)}
                    </Text>
                    <Money value={t.amount} />
                  </Group>
                ))
              )}
              <Divider />
              <Group justify="space-between">
                <Text fw={600}>Total</Text>
                {historical && result ? (
                  <Money
                    strong
                    value={String(
                      Number(result.subtotal) + Number(v.freight || 0) + Number(v.adjustment || 0) + Number(invoice?.tax_total ?? 0),
                    )}
                  />
                ) : (
                  <Money value={result?.total} strong />
                )}
              </Group>
              {calc.error && (
                <Text size="xs" c="red">
                  {calc.error.message}
                </Text>
              )}
            </Stack>
          </Card>
        </SimpleGrid>

        <Group justify="flex-end">
          <Button variant="default" onClick={onCancel}>
            Cancel
          </Button>
          {mode === 'revise' ? (
            <Button type="submit" color="orange" loading={save.isPending}>
              Save revision
            </Button>
          ) : (
            <>
              <Button type="submit" variant="light" loading={save.isPending && !save.variables?.issue}>
                Save draft
              </Button>
              <Button
                loading={save.isPending && save.variables?.issue}
                onClick={() => {
                  if (!form.validate().hasErrors) save.mutate({ issue: true })
                }}
              >
                Save & issue
              </Button>
            </>
          )}
        </Group>
      </Stack>
    </form>
  )
}
