import { Center, Checkbox, Group, Loader, Pagination, Paper, ScrollArea, Table, Text } from '@mantine/core'
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

export interface Selection {
  selected: Set<string | number>
  onChange: (selected: Set<string | number>) => void
  /** Rows that cannot be selected show no checkbox. */
  isSelectable?: (key: string | number) => boolean
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
  selection,
}: {
  columns: Column<T>[]
  rows: T[] | undefined
  rowKey: (row: T) => string | number
  loading?: boolean
  empty?: ReactNode
  onRowClick?: (row: T) => void
  page?: PageInfo
  selection?: Selection
}) {
  const pages = page ? Math.max(1, Math.ceil(page.total / page.limit)) : 1
  const selectable = (rows ?? []).map(rowKey).filter((k) => selection?.isSelectable?.(k) ?? true)
  const allSelected = selectable.length > 0 && selectable.every((k) => selection?.selected.has(k))
  const toggle = (key: string | number, on: boolean) => {
    if (!selection) return
    const next = new Set(selection.selected)
    if (on) next.add(key)
    else next.delete(key)
    selection.onChange(next)
  }
  return (
    <Paper withBorder radius="sm">
      <ScrollArea>
        <Table highlightOnHover={!!onRowClick} verticalSpacing="xs" striped>
          <Table.Thead>
            <Table.Tr>
              {selection && (
                <Table.Th w={36}>
                  <Checkbox
                    aria-label="Select all"
                    checked={allSelected}
                    indeterminate={!allSelected && selectable.some((k) => selection.selected.has(k))}
                    onChange={(e) => {
                      const on = e.currentTarget.checked
                      selection.onChange(on ? new Set(selectable) : new Set())
                    }}
                  />
                </Table.Th>
              )}
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
                {selection && (
                  <Table.Td onClick={(e) => e.stopPropagation()}>
                    {(selection.isSelectable?.(rowKey(row)) ?? true) && (
                      <Checkbox
                        aria-label="Select row"
                        checked={selection.selected.has(rowKey(row))}
                        onChange={(e) => toggle(rowKey(row), e.currentTarget.checked)}
                      />
                    )}
                  </Table.Td>
                )}
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
