/*
 * SauMGM - Sauen Management System: billing, sales tax and bookkeeping for small businesses
 * Copyright (C) 2026 J. Thomas Stokkeland - https://www.saumgm.com/
 *
 * This program is free software: you can redistribute it and/or modify it under the terms of the
 * GNU General Public License as published by the Free Software Foundation, either version 3 of
 * the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
 * without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 * See the GNU General Public License for more details. You should have received a copy of the
 * GNU General Public License along with this program (the LICENSE file); if not, see
 * <https://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

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
  IconBriefcase,
  IconChevronDown,
  IconCoin,
  IconLogout,
  IconMoon,
  IconSettings,
  IconShieldLock,
  IconSun,
  IconTools,
  type Icon,
} from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router'

import { api } from '../api/client'
import { useAuth } from '../auth/context'
import { MODULES } from '../modules'
import type { NavItem, NavSection } from '../modules/types'

/** Menu sections in order. Sections without a label show their entries at the top level. */
const SECTIONS: { key: NavSection; label?: string; icon?: Icon }[] = [
  { key: 'home' },
  { key: 'sales', label: 'Sales', icon: IconBriefcase },
  { key: 'money', label: 'Money', icon: IconCoin },
  { key: 'operations', label: 'Operations', icon: IconTools },
  { key: 'reports' },
  { key: 'admin', label: 'Admin', icon: IconShieldLock },
]

const FOLDED_KEY = 'saumgm.nav.folded'

/** Which sections the user folded, remembered in this browser only. */
function useFolded() {
  const [folded, setFolded] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(FOLDED_KEY) ?? '[]') as string[]
    } catch {
      return []
    }
  })
  const toggle = (key: string) => {
    const next = folded.includes(key) ? folded.filter((k) => k !== key) : [...folded, key]
    setFolded(next)
    try {
      localStorage.setItem(FOLDED_KEY, JSON.stringify(next))
    } catch {
      // private window or blocked storage: the menu just forgets
    }
  }
  return [folded, toggle] as const
}

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

  const [folded, toggleFolded] = useFolded()

  const isActive = (to: string) =>
    to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)
  const items = MODULES.flatMap((m) => m.nav)
    .filter((item) => !item.ownerOnly || isOwner)
    .sort((a, b) => a.order - b.order)
  const link = (item: NavItem) => (
    <NavLink
      key={item.to}
      component={Link}
      to={item.to}
      label={item.label}
      leftSection={<item.icon size={18} stroke={1.6} />}
      active={isActive(item.to)}
      onClick={close}
    />
  )

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
          {SECTIONS.map((section) => {
            const entries = items.filter((item) => item.section === section.key)
            if (!entries.length) return null
            if (!section.label || !section.icon) return entries.map(link)
            const SectionIcon = section.icon
            // A folded section still opens while one of its pages is shown.
            const holdsActive = entries.some((item) => isActive(item.to))
            return (
              <NavLink
                key={section.key}
                component="button"
                aria-expanded={holdsActive || !folded.includes(section.key)}
                label={section.label}
                leftSection={<SectionIcon size={18} stroke={1.6} />}
                opened={holdsActive || !folded.includes(section.key)}
                onChange={() => !holdsActive && toggleFolded(section.key)}
                childrenOffset={14}
              >
                {entries.map(link)}
              </NavLink>
            )
          })}
        </ScrollArea>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  )
}
