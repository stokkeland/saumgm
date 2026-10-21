import { Button, Paper, PasswordInput, Stack, Text } from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation } from '@tanstack/react-query'

import { api, unwrap } from '../api/client'
import { useAuth } from '../auth/context'
import { PageHeader } from '../components/ui'
import { notifyError, notifySaved } from '../lib/notify'

export function AccountPage() {
  const { me } = useAuth()
  const form = useForm({
    initialValues: { current_password: '', new_password: '', repeat: '' },
    validate: {
      new_password: (v) => (v.length >= 10 ? null : 'At least 10 characters'),
      repeat: (v, values) => (v === values.new_password ? null : 'Passwords do not match'),
    },
  })
  const change = useMutation({
    mutationFn: async ({ current_password, new_password }: typeof form.values) =>
      unwrap(await api.POST('/api/auth/password', { body: { current_password, new_password } })),
    onSuccess: () => {
      form.reset()
      notifySaved('Password changed; other devices were signed out')
    },
    onError: notifyError,
  })

  return (
    <>
      <PageHeader title="My account" subtitle={`${me.user.display_name} · ${me.user.email}`} />
      <Paper withBorder p="md" maw={420}>
        <form onSubmit={form.onSubmit((values) => change.mutate(values))}>
          <Stack>
            <Text fw={600}>Change password</Text>
            <PasswordInput
              label="Current password"
              autoComplete="current-password"
              {...form.getInputProps('current_password')}
            />
            <PasswordInput
              label="New password"
              autoComplete="new-password"
              {...form.getInputProps('new_password')}
            />
            <PasswordInput
              label="Repeat new password"
              autoComplete="new-password"
              {...form.getInputProps('repeat')}
            />
            <Button type="submit" loading={change.isPending}>
              Change password
            </Button>
          </Stack>
        </form>
      </Paper>
    </>
  )
}
