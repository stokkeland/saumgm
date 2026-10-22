import {
  ActionIcon,
  Button,
  Card,
  Checkbox,
  FileButton,
  Group,
  Image,
  Modal,
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
import { modals } from '@mantine/modals'
import { IconPencil, IconPlus, IconTrash, IconUpload } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, send, unwrap, type Schemas } from '../../api/client'
import { useOrganization } from '../../api/lookups'
import { useAuth } from '../../auth/context'
import { ME_KEY } from '../../auth/context'
import { DateText } from '../../components/ui'
import { labelOf } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'

type Org = Schemas['OrganizationOut']

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

function BusinessForm({ org }: { org: Org }) {
  const { isOwner } = useAuth()
  const queryClient = useQueryClient()
  const form = useForm({
    initialValues: {
      legal_name: org.legal_name,
      display_name: org.display_name,
      payable_to: org.payable_to ?? '',
      tagline: org.tagline ?? '',
      phone: org.phone ?? '',
      email: org.email ?? '',
      website: org.website ?? '',
      tax_id: org.tax_id ?? '',
      country_code: org.country_code,
      currency_code: org.currency_code,
      locale: org.locale,
      timezone: org.timezone,
      fiscal_year_start_month: String(org.fiscal_year_start_month),
      tax_label: org.tax_label,
      tax_basis: org.tax_basis,
      default_terms_days: org.default_terms_days,
      invoice_revision_owner_only: org.invoice_revision_owner_only,
      footer_text: org.footer_text ?? '',
    },
  })
  const save = useMutation({
    mutationFn: async (v: typeof form.values) =>
      unwrap(
        await api.PATCH('/api/settings/organization', {
          body: {
            ...v,
            payable_to: v.payable_to.trim() || null,
            tagline: v.tagline.trim() || null,
            phone: v.phone.trim() || null,
            email: v.email.trim() || null,
            website: v.website.trim() || null,
            tax_id: v.tax_id.trim() || null,
            footer_text: v.footer_text.trim() || null,
            country_code: v.country_code.toUpperCase(),
            currency_code: v.currency_code.toUpperCase(),
            fiscal_year_start_month: Number(v.fiscal_year_start_month),
            tax_basis: v.tax_basis as Org['tax_basis'],
          },
        }),
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(['organization'], saved)
      queryClient.invalidateQueries({ queryKey: ME_KEY })
      notifySaved('Business settings saved')
    },
    onError: notifyError,
  })
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <fieldset disabled={!isOwner} style={{ border: 0, padding: 0, margin: 0 }}>
        <Stack>
          <Card withBorder>
            <Text fw={600} mb="sm">
              Identity
            </Text>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <TextInput label="Legal name" {...form.getInputProps('legal_name')} />
              <TextInput label="Display name" {...form.getInputProps('display_name')} />
              <TextInput label="Make checks payable to" {...form.getInputProps('payable_to')} />
              <TextInput label="Tagline" {...form.getInputProps('tagline')} />
              <TextInput label="Phone" {...form.getInputProps('phone')} />
              <TextInput label="Email" {...form.getInputProps('email')} />
              <TextInput label="Website" {...form.getInputProps('website')} />
              <TextInput label="Tax ID" {...form.getInputProps('tax_id')} />
            </SimpleGrid>
            <Textarea mt="sm" label="Invoice footer" autosize {...form.getInputProps('footer_text')} />
          </Card>
          <Card withBorder>
            <Text fw={600} mb="sm">
              Country, currency and formats
            </Text>
            <SimpleGrid cols={{ base: 1, sm: 3 }}>
              <TextInput label="Country code" description="ISO, e.g. US, CA" maxLength={2} {...form.getInputProps('country_code')} />
              <TextInput label="Currency" description="ISO, e.g. USD, CAD, EUR" maxLength={3} {...form.getInputProps('currency_code')} />
              <TextInput label="Number and date style" description="e.g. en-US, en-CA, nb-NO" {...form.getInputProps('locale')} />
              <TextInput label="Time zone" description="e.g. America/New_York" {...form.getInputProps('timezone')} />
              <Select label="Fiscal year starts" data={MONTHS.map((m, i) => ({ value: String(i + 1), label: m }))} {...form.getInputProps('fiscal_year_start_month')} />
            </SimpleGrid>
          </Card>
          <Card withBorder>
            <Text fw={600} mb="sm">
              Invoicing and tax
            </Text>
            <SimpleGrid cols={{ base: 1, sm: 3 }}>
              <NumberInput label="Default payment terms (days)" min={0} allowDecimal={false} {...form.getInputProps('default_terms_days')} />
              <TextInput label="Name of the tax" description="Sales Tax, VAT, GST/HST…" {...form.getInputProps('tax_label')} />
              <Select
                label="Report tax by"
                data={[
                  { value: 'accrual', label: 'Invoice date (accrual)' },
                  { value: 'cash', label: 'Payment date (cash)' },
                ]}
                {...form.getInputProps('tax_basis')}
              />
            </SimpleGrid>
            <Checkbox
              mt="md"
              label="Only the owner may revise issued invoices"
              {...form.getInputProps('invoice_revision_owner_only', { type: 'checkbox' })}
            />
          </Card>
          {isOwner && (
            <Group justify="flex-end">
              <Button type="submit" loading={save.isPending} disabled={!form.isDirty()}>
                Save
              </Button>
            </Group>
          )}
        </Stack>
      </fieldset>
    </form>
  )
}

function LogoCard({ org }: { org: Org }) {
  const { isOwner } = useAuth()
  const queryClient = useQueryClient()
  const change = useMutation({
    mutationFn: async (file: File | null) => {
      if (!file) return send('DELETE', '/api/settings/logo')
      const body = new FormData()
      body.append('file', file)
      return send('PUT', '/api/settings/logo', body)
    },
    onSuccess: (_, file) => {
      queryClient.invalidateQueries({ queryKey: ['organization'] })
      notifySaved(file ? 'Logo saved' : 'Logo removed')
    },
    onError: notifyError,
  })
  return (
    <Card withBorder>
      <Text fw={600} mb="sm">
        Logo
      </Text>
      <Group align="center">
        {org.logo_file_id ? (
          // the file id in the URL makes the browser fetch a replaced logo
          <Image src={`/api/settings/logo?v=${org.logo_file_id}`} alt="Business logo" h={60} w="auto" fit="contain" />
        ) : (
          <Text size="sm" c="dimmed">
            No logo; invoices show the business name instead.
          </Text>
        )}
        {isOwner && (
          <Group gap="xs" ml="auto">
            <FileButton accept="image/png,image/jpeg,image/gif" onChange={(file) => file && change.mutate(file)}>
              {(props) => (
                <Button variant="light" leftSection={<IconUpload size={16} />} loading={change.isPending} {...props}>
                  {org.logo_file_id ? 'Replace' : 'Upload'}
                </Button>
              )}
            </FileButton>
            {org.logo_file_id && (
              <Button variant="subtle" color="red" onClick={() => change.mutate(null)}>
                Remove
              </Button>
            )}
          </Group>
        )}
      </Group>
      <Text size="xs" c="dimmed" mt="xs">
        PNG, JPEG or GIF, shown at the top of invoices, receipts and deposit slips. A wide image works
        best.
      </Text>
    </Card>
  )
}

export function BusinessTab() {
  const { data: org } = useOrganization()
  return org ? (
    <Stack>
      <LogoCard org={org} />
      <BusinessForm key={org.id} org={org} />
    </Stack>
  ) : null
}

// -- addresses ------------------------------------------------------------------------------------

type OrgAddress = Schemas['OrgAddressOut']
const ORG_ADDRESS_TYPES = [
  { value: 'remit', label: 'Remit-to (on invoices)' },
  { value: 'physical', label: 'Physical' },
  { value: 'billing', label: 'Billing' },
  { value: 'other', label: 'Other' },
]

function OrgAddressForm({ address, onClose }: { address?: OrgAddress; onClose: () => void }) {
  const queryClient = useQueryClient()
  const form = useForm({
    initialValues: {
      address_type: address?.address_type ?? 'remit',
      line1: address?.line1 ?? '',
      line2: address?.line2 ?? '',
      city: address?.city ?? '',
      region: address?.region ?? '',
      postal_code: address?.postal_code ?? '',
      country_code: address?.country_code ?? '',
      phone: address?.phone ?? '',
      effective_from: address?.effective_from ?? '',
      effective_to: address?.effective_to ?? '',
    },
  })
  const save = useMutation({
    mutationFn: async (v: typeof form.values) => {
      const body = {
        address_type: v.address_type as OrgAddress['address_type'],
        ...Object.fromEntries(
          (['line1', 'line2', 'city', 'region', 'postal_code', 'country_code', 'phone', 'effective_from', 'effective_to'] as const).map(
            (k) => [k, v[k].trim() || null],
          ),
        ),
      }
      return address
        ? unwrap(await api.PATCH('/api/settings/addresses/{address_id}', { params: { path: { address_id: address.id } }, body }))
        : unwrap(await api.POST('/api/settings/addresses', { body }))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org-addresses'] })
      notifySaved('Address saved')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={address ? 'Edit address' : 'Add address'}>
      <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
        <Stack>
          <Select label="Type" data={ORG_ADDRESS_TYPES} {...form.getInputProps('address_type')} />
          <TextInput label="Address line 1" {...form.getInputProps('line1')} />
          <TextInput label="Address line 2" {...form.getInputProps('line2')} />
          <SimpleGrid cols={2}>
            <TextInput label="City" {...form.getInputProps('city')} />
            <TextInput label="State / province" {...form.getInputProps('region')} />
            <TextInput label="Postal code" {...form.getInputProps('postal_code')} />
            <TextInput label="Country code" maxLength={2} {...form.getInputProps('country_code')} />
            <TextInput label="Phone" {...form.getInputProps('phone')} />
          </SimpleGrid>
          <SimpleGrid cols={2}>
            <TextInput type="date" label="Valid from" {...form.getInputProps('effective_from')} />
            <TextInput type="date" label="Valid to" description="Empty: current" {...form.getInputProps('effective_to')} />
          </SimpleGrid>
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

export function AddressesTab() {
  const { isOwner } = useAuth()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<OrgAddress | 'new' | null>(null)
  const { data } = useQuery({
    queryKey: ['org-addresses'],
    queryFn: async () => unwrap(await api.GET('/api/settings/addresses')),
  })
  const remove = useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.DELETE('/api/settings/addresses/{address_id}', { params: { path: { address_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['org-addresses'] }),
    onError: notifyError,
  })
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Text size="sm" c="dimmed">
          Old documents use the address that was valid at their date.
        </Text>
        {isOwner && (
          <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing('new')}>
            Add address
          </Button>
        )}
      </Group>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Type</Table.Th>
            <Table.Th>Address</Table.Th>
            <Table.Th>Valid</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {data?.map((a) => (
            <Table.Tr key={a.id} c={a.effective_to ? 'dimmed' : undefined}>
              <Table.Td>{labelOf(ORG_ADDRESS_TYPES, a.address_type)}</Table.Td>
              <Table.Td>{[a.line1, a.line2, a.city, a.region, a.postal_code, a.country_code].filter(Boolean).join(', ')}</Table.Td>
              <Table.Td>
                {a.effective_from || a.effective_to ? (
                  <>
                    <DateText value={a.effective_from} /> – {a.effective_to ? <DateText value={a.effective_to} /> : 'now'}
                  </>
                ) : (
                  'Current'
                )}
              </Table.Td>
              <Table.Td>
                {isOwner && (
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    <ActionIcon variant="subtle" aria-label="Edit address" onClick={() => setEditing(a)}>
                      <IconPencil size={16} />
                    </ActionIcon>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label="Delete address"
                      onClick={() =>
                        modals.openConfirmModal({
                          title: 'Delete this address?',
                          labels: { confirm: 'Delete', cancel: 'Cancel' },
                          confirmProps: { color: 'red' },
                          onConfirm: () => remove.mutate(a.id),
                        })
                      }
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Group>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {editing && <OrgAddressForm address={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
    </Card>
  )
}

// -- numbering ------------------------------------------------------------------------------------

const SEQUENCE_LABELS: Record<string, string> = {
  invoice: 'Invoices',
  credit_note: 'Credit notes',
  party: 'Contacts',
}

function SequenceRow({ seq }: { seq: Schemas['SequenceOut'] }) {
  const { isOwner } = useAuth()
  const queryClient = useQueryClient()
  const [next, setNext] = useState<number | string>(seq.next_value)
  const [prefix, setPrefix] = useState(seq.prefix)
  const save = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.PATCH('/api/settings/numbering/{name}', {
          params: { path: { name: seq.name } },
          body: { next_value: Number(next), prefix },
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sequences'] })
      notifySaved('Numbering saved')
    },
    onError: notifyError,
  })
  const preview = `${prefix}${String(next).padStart(seq.pad_width, '0')}`
  return (
    <Table.Tr>
      <Table.Td>{SEQUENCE_LABELS[seq.name] ?? seq.name}</Table.Td>
      <Table.Td>
        <TextInput aria-label="Prefix" w={100} disabled={!isOwner} value={prefix} onChange={(e) => setPrefix(e.currentTarget.value)} />
      </Table.Td>
      <Table.Td>
        <NumberInput aria-label="Next number" w={140} min={1} allowDecimal={false} disabled={!isOwner} value={next} onChange={setNext} />
      </Table.Td>
      <Table.Td ff="monospace">{preview}</Table.Td>
      <Table.Td>
        {isOwner && (
          <Button size="xs" variant="light" disabled={next === seq.next_value && prefix === seq.prefix} loading={save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
        )}
      </Table.Td>
    </Table.Tr>
  )
}

export function NumberingTab() {
  const { data } = useQuery({
    queryKey: ['sequences'],
    queryFn: async () => unwrap(await api.GET('/api/settings/numbering')),
  })
  return (
    <Card withBorder>
      <Text size="sm" c="dimmed" mb="xs">
        The next number each kind of document or contact gets.
      </Text>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>For</Table.Th>
            <Table.Th>Prefix</Table.Th>
            <Table.Th>Next number</Table.Th>
            <Table.Th>Next looks like</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {data?.map((seq) => <SequenceRow key={`${seq.name}-${seq.next_value}`} seq={seq} />)}
        </Table.Tbody>
      </Table>
    </Card>
  )
}
