import { Center, Group, Loader, Pagination, Paper, ScrollArea, Table, Text } from '@mantine/core'
import type { ReactNode } from 'react'

export interface Column<T> {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  align?: 'left' | 'right' | 'center'
  width?: number | string
  /** Hide on narrow screens. */
  wide?: boolean
}

export interface PageInfo {
  total: number
  limit: number
  offset: number
  onOffset: (offset: number) => void
}

/** A table with loading/empty states, clickable rows and paging. */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  empty = 'Nothing here yet',
  onRowClick,
  page,
}: {
  columns: Column<T>[]
  rows: T[] | undefined
  rowKey: (row: T) => string | number
  loading?: boolean
  empty?: ReactNode
  onRowClick?: (row: T) => void
  page?: PageInfo
}) {
  const pages = page ? Math.max(1, Math.ceil(page.total / page.limit)) : 1
  return (
    <Paper withBorder radius="sm">
      <ScrollArea>
        <Table highlightOnHover={!!onRowClick} verticalSpacing="xs" striped>
          <Table.Thead>
            <Table.Tr>
              {columns.map((col) => (
                <Table.Th
                  key={col.key}
                  style={{ textAlign: col.align, width: col.width }}
                  visibleFrom={col.wide ? 'sm' : undefined}
                >
                  {col.header}
                </Table.Th>
              ))}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows?.map((row) => (
              <Table.Tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                style={onRowClick ? { cursor: 'pointer' } : undefined}
              >
                {columns.map((col) => (
                  <Table.Td
                    key={col.key}
                    style={{ textAlign: col.align }}
                    visibleFrom={col.wide ? 'sm' : undefined}
                  >
                    {col.render(row)}
                  </Table.Td>
                ))}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
      {loading && !rows?.length && (
        <Center p="lg">
          <Loader size="sm" />
        </Center>
      )}
      {!loading && rows?.length === 0 && (
        <Center p="lg">
          <Text c="dimmed">{empty}</Text>
        </Center>
      )}
      {page && page.total > page.limit && (
        <Group justify="space-between" p="xs">
          <Text size="sm" c="dimmed">
            {page.offset + 1}–{Math.min(page.offset + page.limit, page.total)} of {page.total}
          </Text>
          <Pagination
            size="sm"
            total={pages}
            value={Math.floor(page.offset / page.limit) + 1}
            onChange={(p) => page.onOffset((p - 1) * page.limit)}
          />
        </Group>
      )}
    </Paper>
  )
}
