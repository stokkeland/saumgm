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

import { useQuery } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '../../api/client'

export type Article = Schemas['ArticleOut']
export type ArticleSummary = Schemas['ArticleSummary']
export type KbCategory = Schemas['KbCategoryOut']

export function useKbCategories() {
  return useQuery({
    queryKey: ['kb-categories'],
    queryFn: async () => unwrap(await api.GET('/api/kb/categories')),
    staleTime: 5 * 60_000,
  })
}

export function useKbTags() {
  return useQuery({
    queryKey: ['kb-tags'],
    queryFn: async () => unwrap(await api.GET('/api/kb/tags')),
  })
}

/** The categories as select options, indented by depth ("Clients / ACME" shows as "ACME"). */
export function categoryOptions(categories: KbCategory[] | undefined) {
  return (categories ?? []).map((c) => {
    const depth = c.path.split(' / ').length - 1
    return { value: String(c.id), label: `${'\u00a0'.repeat(3 * depth)}${c.name}` }
  })
}
