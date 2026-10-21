/** Small building blocks shared by the pages. */

import {
  Badge,
  Group,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Title,
  type MantineColor,
} from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { IconSearch } from '@tabler/icons-react'
import { useEffect, useState, type ReactNode } from 'react'

import { useAuth } from '../auth/context'
import { formatDate, formatMoney } from '../lib/format'

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <Group justify="space-between" align="flex-start" mb="md" wrap="wrap">
      <Stack gap={2}>
        <Title order={2}>{title}</Title>
        {subtitle && (
          <Text c="dimmed" size="sm" component="div">
            {subtitle}
          </Text>
        )}
      </Stack>
      {actions && <Group gap="xs">{actions}</Group>}
    </Group>
  )
}

export function Money({ value, strong }: { value: string | null | undefined; strong?: boolean }) {
  const { locale } = useAuth()
  return (
    <Text span fw={strong ? 600 : undefined} style={{ whiteSpace: 'nowrap' }}>
      {formatMoney(value, locale)}
    </Text>
  )
}

export function DateText({ value }: { value: string | null | undefined }) {
  const { locale } = useAuth()
  return (
    <Text span style={{ whiteSpace: 'nowrap' }}>
      {formatDate(value, locale.locale)}
    </Text>
  )
}

/** A search box that reports its value after the user pauses typing. */
export function SearchInput({
  value,
  onChange,
  placeholder = 'Search',
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
}) {
  const [text, setText] = useState(value)
  const [debounced] = useDebouncedValue(text, 300)
  useEffect(() => {
    if (debounced !== value) onChange(debounced)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to typing
  }, [debounced])
  return (
    <TextInput
      leftSection={<IconSearch size={16} />}
      placeholder={placeholder}
      value={text}
      onChange={(event) => setText(event.currentTarget.value)}
      w={{ base: '100%', sm: 280 }}
    />
  )
}

export type ArchiveFilterValue = 'current' | 'archived' | 'all'

export function ArchiveFilter({
  value,
  onChange,
}: {
  value: ArchiveFilterValue
  onChange: (value: ArchiveFilterValue) => void
}) {
  return (
    <SegmentedControl
      size="xs"
      value={value}
      onChange={(v) => onChange(v as ArchiveFilterValue)}
      data={[
        { value: 'current', label: 'Current' },
        { value: 'archived', label: 'Archived' },
        { value: 'all', label: 'All' },
      ]}
    />
  )
}

const PAYMENT_STATUS: Record<string, { color: MantineColor; label: string }> = {
  draft: { color: 'gray', label: 'Draft' },
  unpaid: { color: 'blue', label: 'Unpaid' },
  partially_paid: { color: 'yellow', label: 'Partially paid' },
  paid: { color: 'green', label: 'Paid' },
  overpaid: { color: 'grape', label: 'Overpaid' },
  void: { color: 'red', label: 'Void' },
  credit: { color: 'teal', label: 'Credit note' },
}

export function PaymentStatusBadge({ status, overdue }: { status: string; overdue?: boolean }) {
  if (overdue) {
    return (
      <Badge color="red" variant="light">
        Overdue
      </Badge>
    )
  }
  const s = PAYMENT_STATUS[status] ?? { color: 'gray', label: status }
  return (
    <Badge color={s.color} variant="light">
      {s.label}
    </Badge>
  )
}

export function ArchivedBadge({ at }: { at: string | null | undefined }) {
  return at ? (
    <Badge color="gray" variant="outline" size="sm">
      Archived
    </Badge>
  ) : null
}
