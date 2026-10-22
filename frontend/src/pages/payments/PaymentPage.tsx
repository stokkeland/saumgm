import {
  ActionIcon,
  Alert,
  Anchor,
  Button,
  Card,
  Grid,
  Group,
  Loader,
  Menu,
  Modal,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { modals } from '@mantine/modals'
import { IconArchive, IconDots, IconPencil, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { HistoryPanel } from '../../components/HistoryPanel'
import { ArchivedBadge, DateText, Money, PageHeader, PdfButton } from '../../components/ui'
import { labelOf, PAYMENT_CHANNELS, PAYMENT_METHODS } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'
import { PaymentStateBadge } from './PaymentsPage'

type Payment = Schemas['PaymentOut']

function EditPayment({ payment, onClose }: { payment: Payment; onClose: () => void }) {
  const queryClient = useQueryClient()
  const form = useForm({
    initialValues: {
      received_date: payment.received_date ?? '',
      amount: Number(payment.amount),
      method: payment.method as string | null,
      channel: payment.channel as string | null,
      reference: payment.reference ?? '',
      notes: payment.notes ?? '',
    },
  })
  const save = useMutation({
    mutationFn: async (v: typeof form.values) =>
      unwrap(
        await api.PATCH('/api/payments/{payment_id}', {
          params: { path: { payment_id: payment.id } },
          body: {
            received_date: v.received_date || null,
            amount: String(v.amount),
            method: v.method as Payment['method'],
            channel: v.channel as Payment['channel'],
            reference: v.reference.trim() || null,
            notes: v.notes.trim() || null,
            reallocate: false,
          },
        }),
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(['payment', saved.id], saved)
      queryClient.invalidateQueries({ queryKey: ['payments'] })
      notifySaved('Payment saved')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title="Edit payment">
      <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
        <Stack>
          <SimpleGrid cols={2}>
            <TextInput type="date" label="Received" {...form.getInputProps('received_date')} />
            <NumberInput label="Amount" min={0} decimalScale={2} {...form.getInputProps('amount')} />
            <Select label="Method" data={PAYMENT_METHODS} {...form.getInputProps('method')} />
            <Select label="Received by" clearable data={PAYMENT_CHANNELS} {...form.getInputProps('channel')} />
          </SimpleGrid>
          <TextInput label="Reference" {...form.getInputProps('reference')} />
          <Textarea label="Notes" autosize {...form.getInputProps('notes')} />
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

export function PaymentPage() {
  const { id } = useParams()
  const paymentId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { canEdit, isOwner } = useAuth()
  const [editing, setEditing] = useState(false)
  const { data: payment, error } = useQuery({
    queryKey: ['payment', paymentId],
    queryFn: async () =>
      unwrap(await api.GET('/api/payments/{payment_id}', { params: { path: { payment_id: paymentId } } })),
  })

  const done = (message: string) => (saved?: Payment) => {
    if (saved) queryClient.setQueryData(['payment', saved.id], saved)
    queryClient.invalidateQueries({ queryKey: ['payments'] })
    queryClient.invalidateQueries({ queryKey: ['invoices'] })
    queryClient.invalidateQueries({ queryKey: ['invoice'] })
    queryClient.invalidateQueries({ queryKey: ['contact-balance'] })
    notifySaved(message)
  }
  const reapply = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.PATCH('/api/payments/{payment_id}', {
          params: { path: { payment_id: paymentId } },
          body: { reallocate: true },
        }),
      ),
    onSuccess: done('Payment re-applied to open invoices'),
    onError: notifyError,
  })
  const archive = useMutation({
    mutationFn: async (archived: boolean) =>
      unwrap(
        await api.POST(archived ? '/api/payments/{payment_id}/archive' : '/api/payments/{payment_id}/unarchive', {
          params: { path: { payment_id: paymentId } },
        }),
      ),
    onSuccess: (saved) => done(saved.archived_at ? 'Payment archived' : 'Payment restored')(saved),
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE('/api/payments/{payment_id}', { params: { path: { payment_id: paymentId } } })),
    onSuccess: () => {
      done('Payment deleted')()
      navigate('/payments')
    },
    onError: notifyError,
  })

  if (error) return <Text c="red">{error.message}</Text>
  if (!payment) return <Loader />
  const locked = payment.is_historical || payment.deposit_id !== null || payment.archived_at !== null

  return (
    <>
      <PageHeader
        title={
          <Group gap="sm">
            Payment
            <Money value={payment.amount} />
            <PaymentStateBadge payment={payment} />
            <ArchivedBadge at={payment.archived_at} />
          </Group>
        }
        subtitle={
          <Anchor component={Link} to={`/contacts/${payment.party_id}`}>
            {payment.party_name}
          </Anchor>
        }
        actions={
          <>
            <PdfButton href={`/api/payments/${payment.id}/receipt.pdf`} label="Receipt" />
            {canEdit && (
            <>
              {!locked && (
                <Button leftSection={<IconPencil size={16} />} onClick={() => setEditing(true)}>
                  Edit
                </Button>
              )}
              <Menu position="bottom-end">
                <Menu.Target>
                  <ActionIcon variant="default" size="lg" aria-label="More actions">
                    <IconDots size={18} />
                  </ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>
                  {!locked && (
                    <Menu.Item onClick={() => reapply.mutate()}>Re-apply oldest first</Menu.Item>
                  )}
                  {payment.archived_at ? (
                    <Menu.Item leftSection={<IconArchive size={14} />} disabled={!isOwner} onClick={() => archive.mutate(false)}>
                      Unarchive{!isOwner && ' (owner only)'}
                    </Menu.Item>
                  ) : (
                    <Menu.Item leftSection={<IconArchive size={14} />} onClick={() => archive.mutate(true)}>
                      Archive
                    </Menu.Item>
                  )}
                  {!locked && (
                    <Menu.Item
                      color="red"
                      leftSection={<IconTrash size={14} />}
                      onClick={() =>
                        modals.openConfirmModal({
                          title: 'Delete this payment?',
                          children: <Text size="sm">The invoices it paid will be open again.</Text>,
                          labels: { confirm: 'Delete', cancel: 'Cancel' },
                          confirmProps: { color: 'red' },
                          onConfirm: () => remove.mutate(),
                        })
                      }
                    >
                      Delete
                    </Menu.Item>
                  )}
                </Menu.Dropdown>
              </Menu>
            </>
            )}
          </>
        }
      />
      {payment.deposit_id && (
        <Alert mb="md" variant="light">
          This payment is on{' '}
          <Anchor component={Link} to={`/deposits/${payment.deposit_id}`}>
            a deposit
          </Anchor>
          ; remove it from the deposit to change it.
        </Alert>
      )}
      <Grid mb="md">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Card withBorder h="100%">
            <Stack gap={6}>
              <Group justify="space-between">
                <Text size="sm" c="dimmed">
                  Received
                </Text>
                <DateText value={payment.received_date} />
              </Group>
              <Group justify="space-between">
                <Text size="sm" c="dimmed">
                  Method
                </Text>
                <Text size="sm">{labelOf(PAYMENT_METHODS, payment.method) || '—'}</Text>
              </Group>
              <Group justify="space-between">
                <Text size="sm" c="dimmed">
                  Received by
                </Text>
                <Text size="sm">{labelOf(PAYMENT_CHANNELS, payment.channel) || '—'}</Text>
              </Group>
              <Group justify="space-between">
                <Text size="sm" c="dimmed">
                  Reference
                </Text>
                <Text size="sm">{payment.reference || '—'}</Text>
              </Group>
              {payment.notes && (
                <Text size="sm" style={{ whiteSpace: 'pre-wrap' }} mt="xs">
                  {payment.notes}
                </Text>
              )}
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Card withBorder h="100%">
            <Text fw={600} mb="xs">
              Applied to
            </Text>
            <Table>
              <Table.Tbody>
                {payment.allocations.map((a) => (
                  <Table.Tr key={a.invoice_id}>
                    <Table.Td>
                      <Anchor component={Link} to={`/invoices/${a.invoice_id}`}>
                        Invoice {a.invoice_number}
                      </Anchor>
                    </Table.Td>
                    <Table.Td ta="right">
                      <Money value={a.amount} />
                    </Table.Td>
                  </Table.Tr>
                ))}
                <Table.Tr>
                  <Table.Td c="dimmed">Unapplied credit</Table.Td>
                  <Table.Td ta="right">
                    <Money value={payment.unapplied} />
                  </Table.Td>
                </Table.Tr>
              </Table.Tbody>
            </Table>
          </Card>
        </Grid.Col>
      </Grid>
      <Tabs defaultValue="history">
        <Tabs.List mb="md">
          <Tabs.Tab value="history">History</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="history">
          <HistoryPanel entityType="payment" entityId={payment.id} />
        </Tabs.Panel>
      </Tabs>
      {editing && <EditPayment payment={payment} onClose={() => setEditing(false)} />}
    </>
  )
}
