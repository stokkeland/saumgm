import {
  Alert,
  Button,
  Center,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Navigate, useNavigate, useSearchParams } from 'react-router'

import { api, unwrap } from '../api/client'
import { ME_KEY, useMeQuery } from '../auth/context'

export function LoginPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const queryClient = useQueryClient()
  const { data: me } = useMeQuery()
  const next = params.get('next') || '/'

  const form = useForm({
    initialValues: { email: '', password: '' },
    validate: {
      email: (v) => (v.trim() ? null : 'Enter your email'),
      password: (v) => (v ? null : 'Enter your password'),
    },
  })

  const login = useMutation({
    mutationFn: async (values: typeof form.values) =>
      unwrap(await api.POST('/api/auth/login', { body: values })),
    onSuccess: (data) => {
      queryClient.setQueryData(ME_KEY, data)
      navigate(next.startsWith('/') ? next : '/', { replace: true })
    },
  })

  if (me) return <Navigate to={next} replace />

  return (
    <Center mih="100vh" p="md">
      <Paper withBorder shadow="sm" p="xl" radius="md" w={380} maw="100%">
        <form onSubmit={form.onSubmit((values) => login.mutate(values))}>
          <Stack>
            <div>
              <Title order={2}>SauMGM</Title>
              <Text c="dimmed" size="sm">
                Sign in to continue
              </Text>
            </div>
            {login.error && (
              <Alert color="red" variant="light">
                {login.error.message}
              </Alert>
            )}
            <TextInput
              label="Email"
              autoComplete="username"
              autoFocus
              {...form.getInputProps('email')}
            />
            <PasswordInput
              label="Password"
              autoComplete="current-password"
              {...form.getInputProps('password')}
            />
            <Button type="submit" loading={login.isPending} fullWidth>
              Sign in
            </Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  )
}
