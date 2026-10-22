import {
  ActionIcon,
  Anchor,
  Breadcrumbs,
  Button,
  Card,
  Group,
  Modal,
  NumberInput,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
} from '@mantine/core'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, send, unwrap, type Schemas } from '../../api/client'
import { jurisdictionOptions, useJurisdictions, useTaxCategories } from '../../api/lookups'
import { useAuth } from '../../auth/context'
import { DateText } from '../../components/ui'
import { formatRate, todayIso } from '../../lib/format'
import { notifyError, notifySaved } from '../../lib/notify'

type Jurisdiction = Schemas['JurisdictionOut']
const MONTH_OPTIONS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
].map((label, i) => ({ value: String(i + 1), label }))

function RegistrationPeriods({ registrationId, name }: { registrationId: number; name: string }) {
  const { isOwner } = useAuth()
  const queryClient = useQueryClient()
  const [thisYear] = useState(() => new Date().getFullYear())
  const [year, setYear] = useState<string | null>(String(thisYear))
  const [filing, setFiling] = useState<Schemas['TaxPeriod'] | null>(null)
  const [filedOn, setFiledOn] = useState(todayIso())
  const [amount, setAmount] = useState<number | string>('')
  const [reference, setReference] = useState('')
  const { data } = useQuery({
    queryKey: ['tax-periods', registrationId, year],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/tax/periods', {
          params: { query: { registration_id: registrationId, year: Number(year) } },
        }),
      ),
  })
  const mark = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/tax/filings', {
          body: {
            registration_id: registrationId,
            period_start: filing!.period_start,
            filed_on: filedOn,
            amount_paid: amount === '' ? null : String(amount),
            reference: reference.trim() || null,
          },
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tax-periods', registrationId] })
      setFiling(null)
      notifySaved('Marked as filed')
    },
    onError: notifyError,
  })
  const unmark = useMutation({
    mutationFn: (id: number) => send('DELETE', `/api/tax/filings/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tax-periods', registrationId] }),
    onError: notifyError,
  })
  return (
    <Card withBorder mb="sm">
      <Group justify="space-between" mb="xs">
        <Text fw={600} size="sm">
          {name}: filing periods starting in
        </Text>
        <Select
          aria-label="Year"
          w={100}
          size="xs"
          data={[0, 1, 2, 3, 4, 5].map((i) => String(thisYear + 1 - i))}
          value={year}
          onChange={setYear}
        />
      </Group>
      <Table>
        <Table.Tbody>
          {data?.map((p) => (
            <Table.Tr key={p.period_start}>
              <Table.Td>
                <DateText value={p.period_start} /> – <DateText value={p.period_end} />
              </Table.Td>
              <Table.Td>
                {p.filing ? (
                  <Text size="sm" c="green">
                    Filed <DateText value={p.filing.filed_on} />
                    {p.filing.reference && ` · ${p.filing.reference}`}
                  </Text>
                ) : (
                  <Text size="sm" c="dimmed">
                    Not filed
                  </Text>
                )}
              </Table.Td>
              <Table.Td ta="right">
                {isOwner &&
                  (p.filing ? (
                    <Button size="xs" variant="subtle" color="red" onClick={() => unmark.mutate(p.filing!.id)}>
                      Unmark
                    </Button>
                  ) : (
                    <Button size="xs" variant="light" onClick={() => setFiling(p)}>
                      Mark filed
                    </Button>
                  ))}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {filing && (
        <Modal opened onClose={() => setFiling(null)} title="Mark period as filed">
          <Stack>
            <Text size="sm">
              <DateText value={filing.period_start} /> – <DateText value={filing.period_end} />
            </Text>
            <TextInput type="date" label="Filed on" value={filedOn} onChange={(e) => setFiledOn(e.currentTarget.value)} />
            <NumberInput label="Amount paid" min={0} decimalScale={2} value={amount} onChange={setAmount} />
            <TextInput label="Confirmation / reference" value={reference} onChange={(e) => setReference(e.currentTarget.value)} />
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setFiling(null)}>
                Cancel
              </Button>
              <Button loading={mark.isPending} onClick={() => mark.mutate()}>
                Mark filed
              </Button>
            </Group>
          </Stack>
        </Modal>
      )}
    </Card>
  )
}

const CHILD_LEVEL: Record<string, Jurisdiction['level']> = {
  country: 'state',
  state: 'county',
  county: 'city',
  city: 'other',
  other: 'other',
}

function Registrations() {
  const { isOwner } = useAuth()
  const queryClient = useQueryClient()
  const { data: jurisdictions } = useJurisdictions()
  const { data } = useQuery({ queryKey: ['tax-registrations'], queryFn: async () => unwrap(await api.GET('/api/tax/registrations')) })
  const [jurisdiction, setJurisdiction] = useState<string | null>(null)
  const [number, setNumber] = useState('')
  const [frequency, setFrequency] = useState<string | null>('quarterly')
  const [from, setFrom] = useState(todayIso())
  const [startMonth, setStartMonth] = useState<string | null>('1')
  const [periodsOf, setPeriodsOf] = useState<number | null>(null)
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['tax-registrations'] })
  const add = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/tax/registrations', {
          body: {
            jurisdiction_id: Number(jurisdiction),
            registration_number: number.trim() || null,
            filing_frequency: frequency as Schemas['RegistrationIn']['filing_frequency'],
            period_start_month: Number(startMonth ?? 1),
            effective_from: from,
          },
        }),
      ),
    onSuccess: () => {
      refresh()
      setJurisdiction(null)
      setNumber('')
      notifySaved('Registration added')
    },
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: (id: number) => send('DELETE', `/api/tax/registrations/${id}`),
    onSuccess: refresh,
    onError: notifyError,
  })
  const name = (id: number) => jurisdictions?.find((j) => j.id === id)?.name ?? `#${id}`
  return (
    <Card withBorder>
      <Text fw={600}>Where you collect tax</Text>
      <Text size="sm" c="dimmed" mb="xs">
        Tax is only charged in jurisdictions you are registered in (a state registration covers its
        counties and cities).
      </Text>
      {data?.length ? (
        <Table mb="sm">
          <Table.Tbody>
            {data.map((r) => (
              <Table.Tr key={r.id}>
                <Table.Td fw={500}>{name(r.jurisdiction_id)}</Table.Td>
                <Table.Td>{r.registration_number}</Table.Td>
                <Table.Td>
                  {r.filing_frequency ?? 'annual'}, year from {MONTH_OPTIONS[r.period_start_month - 1].label}
                </Table.Td>
                <Table.Td>
                  since <DateText value={r.effective_from} />
                  {r.effective_to && (
                    <>
                      {' '}
                      until <DateText value={r.effective_to} />
                    </>
                  )}
                </Table.Td>
                <Table.Td>
                  <Button size="xs" variant="subtle" onClick={() => setPeriodsOf(periodsOf === r.id ? null : r.id)}>
                    Periods
                  </Button>
                </Table.Td>
                <Table.Td>
                  {isOwner && (
                    <ActionIcon variant="subtle" color="red" aria-label="Remove registration" onClick={() => remove.mutate(r.id)}>
                      <IconTrash size={16} />
                    </ActionIcon>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : null}
      {periodsOf !== null && data?.some((r) => r.id === periodsOf) && (
        <RegistrationPeriods
          registrationId={periodsOf}
          name={name(data.find((r) => r.id === periodsOf)!.jurisdiction_id)}
        />
      )}
      {data?.length ? null : (
        <Text size="sm" c="orange" mb="sm">
          Not registered anywhere yet, so no sales tax is charged.
        </Text>
      )}
      {isOwner && (
        <Group align="flex-end" gap="xs">
          <Select
            label="Jurisdiction"
            searchable
            w={260}
            data={jurisdictionOptions(jurisdictions)}
            value={jurisdiction}
            onChange={(value) => {
              setJurisdiction(value)
              // New York's filing year starts in March (quarters Mar–May, Jun–Aug, Sep–Nov, Dec–Feb).
              const code = jurisdictions?.find((j) => String(j.id) === value)?.code
              setStartMonth(code === 'US-NY' ? '3' : '1')
            }}
          />
          <TextInput label="Registration no." value={number} onChange={(e) => setNumber(e.currentTarget.value)} />
          <Select
            label="Files"
            w={130}
            data={[
              { value: 'monthly', label: 'Monthly' },
              { value: 'quarterly', label: 'Quarterly' },
              { value: 'annual', label: 'Annually' },
            ]}
            value={frequency}
            onChange={setFrequency}
          />
          <Select label="Filing year starts" w={150} data={MONTH_OPTIONS} value={startMonth} onChange={setStartMonth} />
          <TextInput type="date" label="Since" value={from} onChange={(e) => setFrom(e.currentTarget.value)} />
          <Button disabled={!jurisdiction || !from} loading={add.isPending} onClick={() => add.mutate()}>
            Add
          </Button>
        </Group>
      )}
    </Card>
  )
}

function AddChild({ parent, onClose }: { parent: Jurisdiction; onClose: (created?: Jurisdiction) => void }) {
  const queryClient = useQueryClient()
  const level = CHILD_LEVEL[parent.level]
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [reporting, setReporting] = useState('')
  const suggested = `${parent.code}-${name.trim().toUpperCase().replace(/[^A-Z0-9]+/g, '-')}`
  const create = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/tax/jurisdictions', {
          body: {
            parent_id: parent.id,
            level,
            name: name.trim(),
            code: (code.trim() || suggested).toUpperCase(),
            reporting_code: reporting.trim() || null,
            is_active: true,
          },
        }),
      ),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['jurisdictions'] })
      notifySaved(`${created.name} added`)
      onClose(created)
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={() => onClose()} title={`Add a ${level} in ${parent.name}`}>
      <Stack>
        <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <TextInput label="Code" placeholder={suggested} value={code} onChange={(e) => setCode(e.currentTarget.value)} />
        <TextInput label="Reporting code" description="The code used on tax returns, if any" value={reporting} onChange={(e) => setReporting(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={() => onClose()}>
            Cancel
          </Button>
          <Button disabled={!name.trim()} loading={create.isPending} onClick={() => create.mutate()}>
            Add
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function JurisdictionDetail({ jurisdiction, select }: { jurisdiction: Jurisdiction; select: (id: number) => void }) {
  const { isOwner, locale } = useAuth()
  const queryClient = useQueryClient()
  const { data: all } = useJurisdictions()
  const { data: categories } = useTaxCategories()
  const [adding, setAdding] = useState(false)
  const [rateName, setRateName] = useState(jurisdiction.name)
  const [ratePct, setRatePct] = useState<number | string>('')
  const [rateFrom, setRateFrom] = useState(todayIso())

  const { data: rates } = useQuery({
    queryKey: ['tax-rates', jurisdiction.id],
    queryFn: async () =>
      unwrap(await api.GET('/api/tax/jurisdictions/{jurisdiction_id}/rates', { params: { path: { jurisdiction_id: jurisdiction.id } } })),
  })
  const { data: rules } = useQuery({ queryKey: ['tax-rules'], queryFn: async () => unwrap(await api.GET('/api/tax/rules')) })

  const chain: Jurisdiction[] = []
  for (let j: Jurisdiction | undefined = jurisdiction; j; j = all?.find((x) => x.id === j!.parent_id)) chain.unshift(j)
  const children = (all ?? []).filter((j) => j.parent_id === jurisdiction.id)

  const addRate = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/tax/jurisdictions/{jurisdiction_id}/rates', {
          params: { path: { jurisdiction_id: jurisdiction.id } },
          body: { name: rateName.trim(), rate: String(Number(ratePct) / 100), effective_from: rateFrom },
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tax-rates', jurisdiction.id] })
      setRatePct('')
      notifySaved('Rate added')
    },
    onError: notifyError,
  })
  const endRate = useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.PATCH('/api/tax/rates/{rate_id}', { params: { path: { rate_id: id } }, body: { effective_to: todayIso() } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tax-rates', jurisdiction.id] }),
    onError: notifyError,
  })
  const setRule = useMutation({
    mutationFn: async ({ categoryId, value }: { categoryId: number; value: string }) => {
      const existing = rules?.find((r) => r.jurisdiction_id === jurisdiction.id && r.tax_category_id === categoryId)
      if (value === 'inherit') {
        if (existing) await send('DELETE', `/api/tax/rules/${existing.id}`)
        return
      }
      unwrap(
        await api.PUT('/api/tax/rules', {
          body: { jurisdiction_id: jurisdiction.id, tax_category_id: categoryId, is_taxable: value === 'taxable' },
        }),
      )
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tax-rules'] }),
    onError: notifyError,
  })

  return (
    <Stack>
      <Breadcrumbs>
        {chain.map((j) => (
          <Anchor key={j.id} size="sm" onClick={() => select(j.id)}>
            {j.name}
          </Anchor>
        ))}
      </Breadcrumbs>
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <Card withBorder>
          <Text fw={600} mb="xs">
            Rates in {jurisdiction.name}
          </Text>
          {rates?.length ? (
            <Table mb="sm">
              <Table.Tbody>
                {rates.map((r) => (
                  <Table.Tr key={r.id} c={r.effective_to ? 'dimmed' : undefined}>
                    <Table.Td>{r.name}</Table.Td>
                    <Table.Td fw={500}>{formatRate(r.rate, locale.locale)}</Table.Td>
                    <Table.Td>
                      <DateText value={r.effective_from} /> – {r.effective_to ? <DateText value={r.effective_to} /> : 'now'}
                    </Table.Td>
                    <Table.Td>
                      {isOwner && !r.effective_to && (
                        <Button size="xs" variant="subtle" onClick={() => endRate.mutate(r.id)}>
                          End today
                        </Button>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          ) : (
            <Text size="sm" c="dimmed" mb="sm">
              No rate of its own.
            </Text>
          )}
          {isOwner && (
            <Group align="flex-end" gap="xs">
              <TextInput label="Name on invoices" w={180} value={rateName} onChange={(e) => setRateName(e.currentTarget.value)} />
              <NumberInput label="Rate %" w={90} min={0} max={99} decimalScale={4} value={ratePct} onChange={setRatePct} />
              <TextInput type="date" label="From" value={rateFrom} onChange={(e) => setRateFrom(e.currentTarget.value)} />
              <Button disabled={ratePct === '' || !rateName.trim()} loading={addRate.isPending} onClick={() => addRate.mutate()}>
                Add rate
              </Button>
            </Group>
          )}
        </Card>
        <Card withBorder>
          <Text fw={600}>What is taxable in {jurisdiction.name}</Text>
          <Text size="xs" c="dimmed" mb="xs">
            "Inherit" uses the rule of {chain.length > 1 ? chain[chain.length - 2].name : 'the country'} (taxable when nothing says otherwise).
          </Text>
          <Table>
            <Table.Tbody>
              {categories?.map((c) => {
                const rule = rules?.find((r) => r.jurisdiction_id === jurisdiction.id && r.tax_category_id === c.id)
                const value = rule ? (rule.is_taxable ? 'taxable' : 'exempt') : 'inherit'
                return (
                  <Table.Tr key={c.id}>
                    <Table.Td>{c.name}</Table.Td>
                    <Table.Td>
                      <SegmentedControl
                        size="xs"
                        disabled={!isOwner}
                        value={value}
                        onChange={(v) => setRule.mutate({ categoryId: c.id, value: v })}
                        data={[
                          { value: 'inherit', label: 'Inherit' },
                          { value: 'taxable', label: 'Taxable' },
                          { value: 'exempt', label: 'Not taxable' },
                        ]}
                      />
                    </Table.Td>
                  </Table.Tr>
                )
              })}
            </Table.Tbody>
          </Table>
        </Card>
      </SimpleGrid>
      <Card withBorder>
        <Group justify="space-between" mb="xs">
          <Text fw={600}>Places in {jurisdiction.name}</Text>
          {isOwner && (
            <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setAdding(true)}>
              Add {CHILD_LEVEL[jurisdiction.level]}
            </Button>
          )}
        </Group>
        {children.length === 0 ? (
          <Text size="sm" c="dimmed">
            None yet
          </Text>
        ) : (
          <Group gap="xs">
            {children.map((j) => (
              <Button key={j.id} size="xs" variant="default" onClick={() => select(j.id)}>
                {j.name}
              </Button>
            ))}
          </Group>
        )}
      </Card>
      {adding && (
        <AddChild
          parent={jurisdiction}
          onClose={(created) => {
            setAdding(false)
            if (created) select(created.id)
          }}
        />
      )}
    </Stack>
  )
}

export function TaxTab() {
  const { data: jurisdictions } = useJurisdictions()
  const [selected, setSelected] = useState<number | null>(null)
  const current =
    jurisdictions?.find((j) => j.id === selected) ?? jurisdictions?.find((j) => j.code === 'US-NY') ?? jurisdictions?.[0]
  return (
    <Stack>
      <Registrations />
      <Card withBorder>
        <Group justify="space-between" mb="md">
          <Text fw={600}>Jurisdictions and rates</Text>
          <Select
            aria-label="Jurisdiction"
            searchable
            w={320}
            data={jurisdictionOptions(jurisdictions)}
            value={current ? String(current.id) : null}
            onChange={(v) => v && setSelected(Number(v))}
          />
        </Group>
        {current && <JurisdictionDetail key={current.id} jurisdiction={current} select={setSelected} />}
      </Card>
    </Stack>
  )
}
