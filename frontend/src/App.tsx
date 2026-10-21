import {
  ActionIcon,
  AppShell,
  Badge,
  Card,
  Group,
  Loader,
  Stack,
  Text,
  Title,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core'
import { useQuery } from '@tanstack/react-query'

import { api, type Health } from './api/client'

async function fetchHealth(): Promise<Health> {
  // The API answers 503 with a Health body when the database is down, so read it either way.
  const { data, error } = await api.GET('/api/health')
  const health = data ?? (error as Health | undefined)
  if (!health) throw new Error('No response from the API')
  return health
}

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme()
  const scheme = useComputedColorScheme('light')
  return (
    <ActionIcon
      variant="default"
      aria-label="Toggle color scheme"
      onClick={() => setColorScheme(scheme === 'dark' ? 'light' : 'dark')}
    >
      {scheme === 'dark' ? '☀' : '☾'}
    </ActionIcon>
  )
}

function SystemStatus() {
  const { data, error, isPending } = useQuery({ queryKey: ['health'], queryFn: fetchHealth })

  if (isPending) return <Loader size="sm" />
  if (error) {
    return (
      <Group>
        <Badge color="red">API unreachable</Badge>
        <Text size="sm" c="dimmed">
          {error.message}
        </Text>
      </Group>
    )
  }
  return (
    <Stack gap="xs">
      <Group>
        <Text w={90}>API</Text>
        <Badge color={data.status === 'ok' ? 'green' : 'red'}>{data.status}</Badge>
        <Text size="sm" c="dimmed">
          v{data.version}
        </Text>
      </Group>
      <Group>
        <Text w={90}>Database</Text>
        <Badge color={data.database === 'ok' ? 'green' : 'red'}>{data.database}</Badge>
        <Text size="sm" c="dimmed">
          {data.database_version}
        </Text>
      </Group>
    </Stack>
  )
}

export default function App() {
  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Title order={3}>SauMGM</Title>
          <ColorSchemeToggle />
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Card withBorder maw={480}>
          <Title order={4} mb="sm">
            System status
          </Title>
          <SystemStatus />
        </Card>
      </AppShell.Main>
    </AppShell>
  )
}
