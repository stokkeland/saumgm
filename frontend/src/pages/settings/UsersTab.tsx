import { Badge, Button, Card, Group, Modal, PasswordInput, Select, Stack, Table, Text, TextInput } from '@mantine/core'
import { useForm } from '@mantine/form'
import { IconPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { formatDateTime } from '../../lib/format'
import { notifyError, notifySaved } from '../../lib/notify'

type UserRow = Schemas['UserListItem']
const ROLES = [
  { value: 'owner', label: 'Owner — everything' },
  { value: 'bookkeeper', label: 'Bookkeeper — day-to-day work' },
  { value: 'viewer', label: 'Viewer — read only' },
]

function AddUser({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const form = useForm({
    initialValues: { email: '', display_name: '', role: 'bookkeeper', password: '' },
    validate: {
      email: (v) => (v.includes('@') ? null : 'Enter an email address'),
      display_name: (v) => (v.trim() ? null : 'Required'),
      password: (v) => (v.length >= 10 ? null : 'At least 10 characters'),
    },
  })
  const save = useMutation({
    mutationFn: async (v: typeof form.values) =>
      unwrap(await api.POST('/api/users', { body: { ...v, role: v.role as UserRow['role'] } })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      notifySaved('User added; give them their password')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title="Add user">
      <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
        <Stack>
          <TextInput label="Email (sign-in name)" {...form.getInputProps('email')} />
          <TextInput label="Name" {...form.getInputProps('display_name')} />
          <Select label="Role" data={ROLES} {...form.getInputProps('role')} />
          <PasswordInput label="First password" description="They can change it under My account" {...form.getInputProps('password')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Add user
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

function ResetPassword({ user, onClose }: { user: UserRow; onClose: () => void }) {
  const [password, setPassword] = useState('')
  const reset = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/users/{user_id}/password', {
          params: { path: { user_id: user.id } },
          body: { new_password: password },
        }),
      ),
    onSuccess: () => {
      notifySaved(`Password reset; ${user.display_name} was signed out everywhere`)
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={`New password for ${user.display_name}`}>
      <Stack>
        <PasswordInput label="New password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={password.length < 10} loading={reset.isPending} onClick={() => reset.mutate()}>
            Set password
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export function UsersTab() {
  const { me, locale } = useAuth()
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [resetting, setResetting] = useState<UserRow | null>(null)
  const { data } = useQuery({
    queryKey: ['users'],
    queryFn: async () => unwrap(await api.GET('/api/users')),
  })
  const update = useMutation({
    mutationFn: async ({ id, body }: { id: number; body: Schemas['UserPatch'] }) =>
      unwrap(await api.PATCH('/api/users/{user_id}', { params: { path: { user_id: id } }, body })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      notifySaved('User updated')
    },
    onError: notifyError,
  })
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Text size="sm" c="dimmed">
          People who can sign in. Single sign-on (Microsoft Entra ID and others) can be added later.
        </Text>
        <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setAdding(true)}>
          Add user
        </Button>
      </Group>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Email</Table.Th>
            <Table.Th>Role</Table.Th>
            <Table.Th>Last sign-in</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {data?.map((u) => {
            const self = u.id === me.user.id
            return (
              <Table.Tr key={u.id} c={u.is_active ? undefined : 'dimmed'}>
                <Table.Td>
                  {u.display_name} {!u.is_active && <Badge size="xs" color="gray">Inactive</Badge>}
                </Table.Td>
                <Table.Td>{u.email}</Table.Td>
                <Table.Td>
                  <Select
                    aria-label={`Role of ${u.display_name}`}
                    w={150}
                    size="xs"
                    disabled={self}
                    data={ROLES.map((r) => ({ value: r.value, label: r.value }))}
                    value={u.role}
                    onChange={(role) => role && update.mutate({ id: u.id, body: { role: role as UserRow['role'] } })}
                  />
                </Table.Td>
                <Table.Td>{formatDateTime(u.last_login_at, locale.locale) || 'Never'}</Table.Td>
                <Table.Td>
                  <Group gap="xs" justify="flex-end" wrap="nowrap">
                    <Button size="xs" variant="subtle" onClick={() => setResetting(u)}>
                      Reset password
                    </Button>
                    {!self && (
                      <Button
                        size="xs"
                        variant="subtle"
                        color={u.is_active ? 'red' : undefined}
                        onClick={() => update.mutate({ id: u.id, body: { is_active: !u.is_active } })}
                      >
                        {u.is_active ? 'Deactivate' : 'Activate'}
                      </Button>
                    )}
                  </Group>
                </Table.Td>
              </Table.Tr>
            )
          })}
        </Table.Tbody>
      </Table>
      {adding && <AddUser onClose={() => setAdding(false)} />}
      {resetting && <ResetPassword user={resetting} onClose={() => setResetting(null)} />}
    </Card>
  )
}
