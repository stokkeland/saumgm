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

import { Anchor, Badge, Group, Typography } from '@mantine/core'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router'
import remarkGfm from 'remark-gfm'

import type { ArticleSummary } from './shared'

export function ArticleBadges({ article }: { article: Pick<ArticleSummary, 'status' | 'visibility'> }) {
  return (
    <Group gap={4} wrap="nowrap">
      {article.status === 'draft' && (
        <Badge variant="light" color="gray">
          Draft
        </Badge>
      )}
      {article.visibility === 'shareable' && (
        <Badge variant="light" color="teal">
          Shareable
        </Badge>
      )}
    </Group>
  )
}

/**
 * An article's text. Raw HTML in it is shown as text, never run, and unsafe link addresses
 * (javascript: and the like) are dropped by react-markdown; addresses inside the app open in it.
 */
export function Markdown({ text }: { text: string }) {
  return (
    <Typography>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) =>
            href?.startsWith('/') && !href.startsWith('/api/') ? (
              <Anchor component={Link} to={href}>
                {children}
              </Anchor>
            ) : (
              <Anchor href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </Anchor>
            ),
          img: ({ src, alt }) => <img src={typeof src === 'string' ? src : undefined} alt={alt ?? ''} style={{ maxWidth: '100%' }} />,
        }}
      >
        {text}
      </ReactMarkdown>
    </Typography>
  )
}
