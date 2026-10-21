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
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['tax-registrations'] })
  const add = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/tax/registrations', {
          body: {
            jurisdiction_id: Number(jurisdiction),
            registration_number: number.trim() || null,
            filing_frequency: frequency as Schemas['RegistrationIn']['filing_frequency'],
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
                <Table.Td>{r.filing_frequency}</Table.Td>
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
      ) : (
        <Text size="sm" c="orange" mb="sm">
          Not registered anywhere yet, so no sales tax is charged.
        </Text>
      )}
      {isOwner && (
        <Group align="flex-end" gap="xs">
          <Select label="Jurisdiction" searchable w={260} data={jurisdictionOptions(jurisdictions)} value={jurisdiction} onChange={setJurisdiction} />
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
