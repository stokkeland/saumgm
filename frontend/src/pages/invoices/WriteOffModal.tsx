import { Alert, Button, Group, List, Modal, Stack, Text, Textarea, TextInput } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, unwrap, type Schemas } from '../../api/client'
import { Money } from '../../components/ui'
import { todayIso } from '../../lib/format'
import { notifyError, notifySaved } from '../../lib/notify'

function useRefresh() {
  const queryClient = useQueryClient()
  return () => {
    for (const key of ['invoices', 'invoice', 'dashboard', 'contact-balance']) {
      queryClient.invalidateQueries({ queryKey: [key] })
    }
  }
}

/** Write off one or more uncollectible invoices (bad debt). */
export function WriteOffModal({
  invoiceIds,
  onClose,
}: {
  invoiceIds: number[]
  onClose: (done: boolean) => void
}) {
  const refresh = useRefresh()
  const [reason, setReason] = useState('')
  const [date, setDate] = useState(todayIso())
  const [skipped, setSkipped] = useState<Schemas['Skipped'][]>([])
  const writeOff = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/invoices/write-off', {
          body: { invoice_ids: invoiceIds, reason: reason.trim(), write_off_date: date || null },
        }),
      ),
    onSuccess: (result) => {
      refresh()
      if (result.written_off.length) {
        const total = result.written_off.reduce((sum, w) => sum + Number(w.amount), 0)
        notifySaved(`${result.written_off.length} invoice(s) written off, ${total.toFixed(2)} in total`)
      }
      if (result.skipped.length) setSkipped(result.skipped)
      else onClose(true)
    },
    onError: notifyError,
  })
  const many = invoiceIds.length > 1
  return (
    <Modal opened onClose={() => onClose(skipped.length > 0)} title={many ? `Write off ${invoiceIds.length} invoices` : 'Write off as uncollectible'}>
      <Stack>
        {skipped.length > 0 ? (
          <>
            <Alert color="orange" variant="light" title="Some invoices were not written off">
              <List size="sm">
                {skipped.map((s) => (
                  <List.Item key={s.invoice_id}>
                    {s.number ?? `#${s.invoice_id}`}: {s.reason}
                  </List.Item>
                ))}
              </List>
            </Alert>
            <Group justify="flex-end">
              <Button onClick={() => onClose(true)}>Close</Button>
            </Group>
          </>
        ) : (
          <>
            <Text size="sm">
              What is still owed is given up: the balance becomes zero and the invoice leaves the
              open and overdue lists. The sale itself still counts. You can undo it if they pay
              after all.
            </Text>
            <Textarea
              label="Reason"
              required
              autosize
              minRows={2}
              placeholder="e.g. Client went out of business; collection attempts failed"
              value={reason}
              onChange={(e) => setReason(e.currentTarget.value)}
            />
            <TextInput type="date" label="Write-off date" value={date} onChange={(e) => setDate(e.currentTarget.value)} />
            <Group justify="flex-end">
              <Button variant="default" onClick={() => onClose(false)}>
                Cancel
              </Button>
              <Button color="dark" disabled={reason.trim().length < 3} loading={writeOff.isPending} onClick={() => writeOff.mutate()}>
                Write off
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Modal>
  )
}

export function UndoWriteOffModal({ invoice, onClose }: { invoice: Schemas['InvoiceOut']; onClose: () => void }) {
  const refresh = useRefresh()
  const [reason, setReason] = useState('')
  const undo = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/invoices/{invoice_id}/undo-write-off', {
          params: { path: { invoice_id: invoice.id } },
          body: { reason: reason.trim() },
        }),
      ),
    onSuccess: () => {
      refresh()
      notifySaved('Write-off undone; the balance is owed again')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={`Undo the write-off of invoice ${invoice.number}`}>
      <Stack>
        <Text size="sm">
          <Money value={invoice.write_off_amount} /> becomes owed again.
        </Text>
        <Textarea label="Reason" required autosize value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={reason.trim().length < 3} loading={undo.isPending} onClick={() => undo.mutate()}>
            Undo write-off
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
