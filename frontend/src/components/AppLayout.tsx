import {
  ActionIcon,
  AppShell,
  Burger,
  Group,
  Menu,
  NavLink,
  ScrollArea,
  Text,
  Title,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import {
  IconBuildingBank,
  IconCalendarRepeat,
  IconCash,
  IconChevronDown,
  IconFileInvoice,
  IconHistory,
  IconHome,
  IconLogout,
  IconMoon,
  IconPackage,
  IconReceipt,
  IconSettings,
  IconSun,
  IconUsers,
  type Icon,
} from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, Outlet, useLocation } from 'react-router'

import { api } from '../api/client'
import { useAuth } from '../auth/context'

interface NavItem {
  to: string
  label: string
  icon: Icon
  ownerOnly?: boolean
}

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: IconHome },
  { to: '/contacts', label: 'Contacts', icon: IconUsers },
  { to: '/invoices', label: 'Invoices', icon: IconFileInvoice },
  { to: '/payments', label: 'Payments', icon: IconCash },
  { to: '/deposits', label: 'Deposits', icon: IconBuildingBank },
  { to: '/expenses', label: 'Expenses', icon: IconReceipt },
  { to: '/subscriptions', label: 'Subscriptions', icon: IconCalendarRepeat },
  { to: '/catalog', label: 'Catalog', icon: IconPackage },
  { to: '/settings', label: 'Settings', icon: IconSettings },
  { to: '/audit', label: 'Audit log', icon: IconHistory, ownerOnly: true },
]

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme()
  const scheme = useComputedColorScheme('light')
  return (
    <ActionIcon
      variant="default"
      size="lg"
      aria-label="Toggle light/dark mode"
      onClick={() => setColorScheme(scheme === 'dark' ? 'light' : 'dark')}
    >
      {scheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
    </ActionIcon>
  )
}

export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure()
  const { me, isOwner } = useAuth()
  const location = useLocation()
  const queryClient = useQueryClient()
  const logout = useMutation({
    mutationFn: () => api.POST('/api/auth/logout'),
    onSettled: () => {
      queryClient.clear()
      window.location.assign('/login')
    },
  })

  const isActive = (to: string) =>
    to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Title order={4}>{me.organization.display_name}</Title>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <ColorSchemeToggle />
            <Menu position="bottom-end" withinPortal>
              <Menu.Target>
                <UnstyledButton>
                  <Group gap={4} wrap="nowrap">
                    <Text size="sm" visibleFrom="xs">
                      {me.user.display_name}
                    </Text>
                    <IconChevronDown size={14} />
                  </Group>
                </UnstyledButton>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>
                  {me.user.email} · {me.role}
                </Menu.Label>
                <Menu.Item component={Link} to="/account" leftSection={<IconSettings size={14} />}>
                  My account
                </Menu.Item>
                <Menu.Item
                  color="red"
                  leftSection={<IconLogout size={14} />}
                  onClick={() => logout.mutate()}
                >
                  Sign out
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        <ScrollArea>
          {NAV.filter((item) => !item.ownerOnly || isOwner).map((item) => (
            <NavLink
              key={item.to}
              component={Link}
              to={item.to}
              label={item.label}
              leftSection={<item.icon size={18} stroke={1.6} />}
              active={isActive(item.to)}
              onClick={close}
            />
          ))}
        </ScrollArea>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  )
}
