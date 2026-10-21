import { Badge, Code, Group, Stack, Table, Text, Timeline } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'

import { api, unwrap } from '../api/client'
import { useAuth } from '../auth/context'
import { formatDateTime } from '../lib/format'

const ACTION_COLORS: Record<string, string> = {
  create: 'green',
  update: 'blue',
  delete: 'red',
  issue: 'teal',
  void: 'red',
  revise: 'orange',
  archive: 'gray',
  import: 'gray',
}

function label(entityType: string | null | undefined): string {
  return (entityType ?? '').replaceAll('_', ' ')
}

function value(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}

/** Everything that happened to a record (and its lines, addresses, ...), newest first. */
export function HistoryPanel({ entityType, entityId }: { entityType: string; entityId: number }) {
  const { locale } = useAuth()
  const { data, isPending } = useQuery({
    queryKey: ['history', entityType, entityId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/history/{entity_type}/{entity_id}', {
          params: { path: { entity_type: entityType, entity_id: String(entityId) }, query: { limit: 200 } },
        }),
      ),
  })
  if (isPending) return <Text c="dimmed">Loading…</Text>
  if (!data?.items.length) return <Text c="dimmed">No recorded changes yet.</Text>

  return (
    <Timeline bulletSize={14} lineWidth={2}>
      {data.items.map((entry) => {
        const changes = Object.entries(entry.changes ?? {}) as [string, [unknown, unknown]][]
        return (
          <Timeline.Item
            key={entry.id}
            color={ACTION_COLORS[entry.action] ?? 'gray'}
            title={
              <Group gap="xs">
                <Badge size="sm" variant="light" color={ACTION_COLORS[entry.action] ?? 'gray'}>
                  {entry.action}
                </Badge>
                {entry.entity_type !== entityType && (
                  <Text size="sm" c="dimmed">
                    {label(entry.entity_type)}
                  </Text>
                )}
                <Text size="sm" c="dimmed">
                  {formatDateTime(entry.occurred_at, locale.locale)} ·{' '}
                  {entry.user_name ?? entry.actor}
                </Text>
              </Group>
            }
          >
            <Stack gap={4} mt={4}>
              {entry.reason && (
                <Text size="sm">
                  <b>Reason:</b> {entry.reason}
                </Text>
              )}
              {changes.length > 0 && entry.action !== 'delete' && (
                <Table withRowBorders={false} verticalSpacing={2} fz="xs">
                  <Table.Tbody>
                    {changes.map(([field, [before, after]]) => (
                      <Table.Tr key={field}>
                        <Table.Td c="dimmed" w={180}>
                          {label(field)}
                        </Table.Td>
                        <Table.Td>
                          {entry.action === 'update' && (
                            <>
                              <Code>{value(before)}</Code> →{' '}
                            </>
                          )}
                          <Code>{value(after)}</Code>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Stack>
          </Timeline.Item>
        )
      })}
    </Timeline>
  )
}
