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

import { IconBook } from '@tabler/icons-react'

import type { AppModule } from '../types'
import { ArticlePage, ArticlesPage, EditArticlePage, NewArticlePage } from './ArticlePages'
import { KbCategoriesPage } from './CategoriesPage'

export const knowledgeModule: AppModule = {
  name: 'knowledge',
  routes: [
    { path: '/kb', element: <ArticlesPage /> },
    { path: '/kb/new', element: <NewArticlePage /> },
    { path: '/kb/categories', element: <KbCategoriesPage /> },
    { path: '/kb/:id', element: <ArticlePage /> },
    { path: '/kb/:id/edit', element: <EditArticlePage /> },
  ],
  nav: [{ to: '/kb', label: 'Knowledge base', icon: IconBook, section: 'operations', order: 20 }],
}
