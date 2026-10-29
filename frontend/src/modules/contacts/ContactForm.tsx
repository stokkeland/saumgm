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
  Button,
  Checkbox,
  Group,
  Modal,
  MultiSelect,
  NumberInput,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Textarea,
  TextInput,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '../../api/client'
import { jurisdictionOptions, useAccounts, useJurisdictions } from '../../api/lookups'
import { ADDRESS_TYPES, ROLE_LABELS } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'

type Detail = Schemas['PartyDetail']
type Role = Schemas['PartyCreate']['roles'][number]

const blankToNull = (v: string) => (v.trim() === '' ? null : v.trim())

/** Create or edit a contact's main details. */
export function ContactForm({
  contact,
  onClose,
  onSaved,
}: {
  contact?: Detail
  onClose: () => void
  onSaved?: (saved: Detail) => void
}) {
  const queryClient = useQueryClient()
  const { data: accounts } = useAccounts()
  const isSelf = contact?.roles.includes('self') ?? false
  const form = useForm({
    initialValues: {
      short_code: contact?.short_code ?? '',
      name: contact?.name ?? '',
      kind: contact?.kind ?? 'company',
      roles: (contact?.roles ?? ['client']) as string[],
      is_active: contact?.is_active ?? true,
      phone: contact?.phone ?? '',
      fax: contact?.fax ?? '',
      email: contact?.email ?? '',
      website: contact?.website ?? '',
      tax_id: contact?.tax_id ?? '',
      default_terms_days: contact?.default_terms_days ?? ('' as number | ''),
      vendor_account_no: contact?.vendor_account_no ?? '',
      default_expense_account_id: contact?.default_expense_account_id
        ? String(contact.default_expense_account_id)
        : (null as string | null),
      notes: contact?.notes ?? '',
    },
    validate: {
      short_code: (v) => (v.trim() ? null : 'Required'),
      name: (v) => (v.trim() ? null : 'Required'),
      roles: (v) => (v.length ? null : 'Pick at least one role'),
    },
  })

  const save = useMutation({
    mutationFn: async (v: typeof form.values) => {
      const body = {
        short_code: v.short_code.trim(),
        name: v.name.trim(),
        kind: v.kind as Detail['kind'],
        roles: v.roles as Role[],
        phone: blankToNull(v.phone),
        fax: blankToNull(v.fax),
        email: blankToNull(v.email),
        website: blankToNull(v.website),
        tax_id: blankToNull(v.tax_id),
        default_terms_days: v.default_terms_days === '' ? null : v.default_terms_days,
        vendor_account_no: blankToNull(v.vendor_account_no),
        default_expense_account_id: v.default_expense_account_id
          ? Number(v.default_expense_account_id)
          : null,
        notes: blankToNull(v.notes),
      }
      if (contact) {
        return unwrap(
          await api.PATCH('/api/contacts/{party_id}', {
            params: { path: { party_id: contact.id } },
            body: { ...body, is_active: v.is_active },
          }),
        )
      }
      return unwrap(await api.POST('/api/contacts', { body: { ...body, addresses: [], people: [] } }))
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ['contacts'] })
      queryClient.setQueryData(['contact', saved.id], saved)
      notifySaved(contact ? 'Contact saved' : `Contact ${saved.party_no} created`)
      onSaved?.(saved)
      onClose()
    },
    onError: notifyError,
  })

  const roleOptions = Object.entries(ROLE_LABELS)
    .filter(([value]) => value !== 'self' || isSelf)
    .map(([value, label]) => ({ value, label, disabled: value === 'self' }))

  return (
    <Modal opened onClose={onClose} title={contact ? `Edit ${contact.name}` : 'New contact'} size="lg">
      <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
        <Stack>
          <SegmentedControl
            data={[
              { value: 'company', label: 'Company' },
              { value: 'person', label: 'Person' },
            ]}
            {...form.getInputProps('kind')}
          />
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <TextInput label="Short code" required {...form.getInputProps('short_code')} />
            <TextInput
              label="Name"
              required
              style={{ gridColumn: 'span 2' }}
              {...form.getInputProps('name')}
            />
          </SimpleGrid>
          <MultiSelect label="Roles" data={roleOptions} {...form.getInputProps('roles')} />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label="Email" {...form.getInputProps('email')} />
            <TextInput label="Phone" {...form.getInputProps('phone')} />
            <TextInput label="Website" {...form.getInputProps('website')} />
            <TextInput label="Fax" {...form.getInputProps('fax')} />
            <TextInput label="Tax ID" {...form.getInputProps('tax_id')} />
            <NumberInput
              label="Payment terms (days)"
              description="Empty: the business default"
              min={0}
              allowDecimal={false}
              {...form.getInputProps('default_terms_days')}
            />
            <TextInput label="Our account no. with this vendor" {...form.getInputProps('vendor_account_no')} />
            <Select
              label="Default expense account"
              clearable
              searchable
              data={(accounts ?? []).map((a) => ({ value: String(a.id), label: `${a.code} ${a.name}` }))}
              {...form.getInputProps('default_expense_account_id')}
            />
          </SimpleGrid>
          <Textarea label="Notes" autosize minRows={2} {...form.getInputProps('notes')} />
          {contact && <Checkbox label="Active" {...form.getInputProps('is_active', { type: 'checkbox' })} />}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              {contact ? 'Save' : 'Create'}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

type Address = Schemas['AddressOut']

export function AddressForm({
  partyId,
  address,
  onClose,
}: {
  partyId: number
  address?: Address
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { data: jurisdictions } = useJurisdictions()
  const form = useForm({
    initialValues: {
      address_type: address?.address_type ?? 'billing',
      is_default: address?.is_default ?? true,
      line1: address?.line1 ?? '',
      line2: address?.line2 ?? '',
      city: address?.city ?? '',
      region: address?.region ?? '',
      postal_code: address?.postal_code ?? '',
      country_code: address?.country_code ?? 'US',
      tax_jurisdiction_id: address?.tax_jurisdiction_id ? String(address.tax_jurisdiction_id) : null,
    },
  })
  const save = useMutation({
    mutationFn: async (v: typeof form.values) => {
      const body = {
        address_type: v.address_type as Address['address_type'],
        is_default: v.is_default,
        line1: blankToNull(v.line1),
        line2: blankToNull(v.line2),
        city: blankToNull(v.city),
        region: blankToNull(v.region),
        postal_code: blankToNull(v.postal_code),
        country_code: blankToNull(v.country_code)?.toUpperCase() ?? null,
        tax_jurisdiction_id: v.tax_jurisdiction_id ? Number(v.tax_jurisdiction_id) : null,
      }
      if (address) {
        return unwrap(
          await api.PATCH('/api/contacts/{party_id}/addresses/{address_id}', {
            params: { path: { party_id: partyId, address_id: address.id } },
            body,
          }),
        )
      }
      return unwrap(
        await api.POST('/api/contacts/{party_id}/addresses', {
          params: { path: { party_id: partyId } },
          body,
        }),
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact', partyId] })
      notifySaved('Address saved')
      onClose()
    },
    onError: notifyError,
  })

  return (
    <Modal opened onClose={onClose} title={address ? 'Edit address' : 'Add address'}>
      <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
        <Stack>
          <Select label="Type" data={ADDRESS_TYPES} {...form.getInputProps('address_type')} />
          <TextInput label="Address line 1" {...form.getInputProps('line1')} />
          <TextInput label="Address line 2" {...form.getInputProps('line2')} />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label="City" {...form.getInputProps('city')} />
            <TextInput label="State / province" {...form.getInputProps('region')} />
            <TextInput label="Postal code" {...form.getInputProps('postal_code')} />
            <TextInput label="Country code" maxLength={2} {...form.getInputProps('country_code')} />
          </SimpleGrid>
          <Select
            label="Sales-tax location"
            description="Empty: worked out from country and state"
            clearable
            searchable
            data={jurisdictionOptions(jurisdictions)}
            {...form.getInputProps('tax_jurisdiction_id')}
          />
          <Checkbox label="Default address of this type" {...form.getInputProps('is_default', { type: 'checkbox' })} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

type Person = Schemas['PersonOut']

export function PersonForm({
  partyId,
  person,
  onClose,
}: {
  partyId: number
  person?: Person
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const form = useForm({
    initialValues: {
      name: person?.name ?? '',
      title: person?.title ?? '',
      phone: person?.phone ?? '',
      mobile: person?.mobile ?? '',
      email: person?.email ?? '',
      is_primary: person?.is_primary ?? false,
      notes: person?.notes ?? '',
    },
    validate: { name: (v) => (v.trim() ? null : 'Required') },
  })
  const save = useMutation({
    mutationFn: async (v: typeof form.values) => {
      const body = {
        name: v.name.trim(),
        title: blankToNull(v.title),
        phone: blankToNull(v.phone),
        mobile: blankToNull(v.mobile),
        email: blankToNull(v.email),
        is_primary: v.is_primary,
        notes: blankToNull(v.notes),
      }
      if (person) {
        return unwrap(
          await api.PATCH('/api/contacts/{party_id}/people/{person_id}', {
            params: { path: { party_id: partyId, person_id: person.id } },
            body,
          }),
        )
      }
      return unwrap(
        await api.POST('/api/contacts/{party_id}/people', {
          params: { path: { party_id: partyId } },
          body,
        }),
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact', partyId] })
      notifySaved('Person saved')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={person ? 'Edit person' : 'Add person'}>
      <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label="Name" required {...form.getInputProps('name')} />
            <TextInput label="Title" {...form.getInputProps('title')} />
            <TextInput label="Email" {...form.getInputProps('email')} />
            <TextInput label="Phone" {...form.getInputProps('phone')} />
            <TextInput label="Mobile" {...form.getInputProps('mobile')} />
          </SimpleGrid>
          <Textarea label="Notes" autosize {...form.getInputProps('notes')} />
          <Checkbox label="Primary contact (used on invoices)" {...form.getInputProps('is_primary', { type: 'checkbox' })} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

type Exemption = Schemas['ExemptionOut']

export function ExemptionForm({
  partyId,
  exemption,
  onClose,
}: {
  partyId: number
  exemption?: Exemption
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { data: jurisdictions } = useJurisdictions()
  const form = useForm({
    initialValues: {
      certificate_type: exemption?.certificate_type ?? '',
      certificate_number: exemption?.certificate_number ?? '',
      jurisdiction_id: exemption?.jurisdiction_id ? String(exemption.jurisdiction_id) : null,
      valid_from: exemption?.valid_from ?? '',
      valid_to: exemption?.valid_to ?? '',
      notes: exemption?.notes ?? '',
    },
    validate: { certificate_type: (v) => (v.trim() ? null : 'Required') },
  })
  const save = useMutation({
    mutationFn: async (v: typeof form.values) => {
      const body = {
        certificate_type: v.certificate_type.trim(),
        certificate_number: blankToNull(v.certificate_number),
        jurisdiction_id: v.jurisdiction_id ? Number(v.jurisdiction_id) : null,
        valid_from: blankToNull(v.valid_from),
        valid_to: blankToNull(v.valid_to),
        notes: blankToNull(v.notes),
      }
      if (exemption) {
        return unwrap(
          await api.PATCH('/api/contacts/{party_id}/tax-exemptions/{exemption_id}', {
            params: { path: { party_id: partyId, exemption_id: exemption.id } },
            body,
          }),
        )
      }
      return unwrap(
        await api.POST('/api/contacts/{party_id}/tax-exemptions', {
          params: { path: { party_id: partyId } },
          body,
        }),
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact', partyId] })
      notifySaved('Tax exemption saved')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={exemption ? 'Edit tax exemption' : 'Add tax exemption'}>
      <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
        <Stack>
          <TextInput
            label="Type"
            placeholder="e.g. Resale (ST-120), Exempt organization, Native American"
            required
            {...form.getInputProps('certificate_type')}
          />
          <TextInput label="Certificate number" {...form.getInputProps('certificate_number')} />
          <Select
            label="Applies in"
            description="Empty: everywhere"
            clearable
            searchable
            data={jurisdictionOptions(jurisdictions)}
            {...form.getInputProps('jurisdiction_id')}
          />
          <SimpleGrid cols={2}>
            <TextInput label="Valid from" type="date" {...form.getInputProps('valid_from')} />
            <TextInput label="Valid to" type="date" {...form.getInputProps('valid_to')} />
          </SimpleGrid>
          <Textarea label="Notes" autosize {...form.getInputProps('notes')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
