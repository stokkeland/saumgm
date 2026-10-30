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
  Anchor,
  Badge,
  Button,
  Card,
  FileButton,
  Grid,
  Group,
  Highlight,
  Loader,
  Modal,
  NavLink,
  Pagination,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  TagsInput,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import {
  IconBold,
  IconCode,
  IconEdit,
  IconH2,
  IconItalic,
  IconLink,
  IconList,
  IconListNumbers,
  IconPaperclip,
  IconPhoto,
  IconPlus,
  IconTable,
  IconTrash,
} from '@tabler/icons-react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { api, send, unwrap } from '../../api/client'
import { useAuth } from '../../auth/context'
import { ContactSelect } from '../../components/ContactSelect'
import { DataTable } from '../../components/DataTable'
import { ArticleEmailButton } from '../../components/EmailDialog'
import { HistoryPanel } from '../../components/HistoryPanel'
import { DateText, PageHeader, PdfButton, SearchInput } from '../../components/ui'
import { formatDateTime } from '../../lib/format'
import { ARTICLE_STATUSES, ARTICLE_VISIBILITIES } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'
import { useUrlState } from '../../lib/useUrlState'
import { ArticleBadges, Markdown } from './Markdown'
import { categoryOptions, useKbCategories, useKbTags, type Article, type ArticleSummary } from './shared'

const LIMIT = 25

function fileName(title: string) {
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60)
  return `${slug.replace(/-+$/, '') || 'article'}.pdf`
}

// -- the list and search ------------------------------------------------------------------------

export function ArticlesPage() {
  const { canEdit } = useAuth()
  const { data: categories } = useKbCategories()
  const { data: tags } = useKbTags()
  const [f, setF] = useUrlState({ q: '', category: '', tag: '', status: '', visibility: '', offset: '0' })
  const { data, isFetching } = useQuery({
    queryKey: ['kb-articles', f],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/kb/articles', {
          params: {
            query: {
              q: f.q || undefined,
              category_id: f.category ? Number(f.category) : undefined,
              tag: f.tag || undefined,
              status: (f.status || undefined) as Article['status'] | undefined,
              visibility: (f.visibility || undefined) as Article['visibility'] | undefined,
              limit: LIMIT,
              offset: Number(f.offset),
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })
  const terms = f.q.split(/\s+/).filter(Boolean)
  const newLink = f.category ? `/kb/new?category=${f.category}` : '/kb/new'
  return (
    <>
      <PageHeader
        title="Knowledge base"
        subtitle="How-tos, notes about clients and servers, policies"
        actions={
          canEdit && (
            <>
              <Button component={Link} to="/kb/categories" variant="default">
                Categories
              </Button>
              <Button component={Link} to={newLink} leftSection={<IconPlus size={16} />}>
                New article
              </Button>
            </>
          )
        }
      />
      <Grid>
        <Grid.Col span={{ base: 12, md: 3 }}>
          <Card withBorder p="xs">
            <NavLink label="All articles" active={!f.category} onClick={() => setF({ category: '' })} />
            {(categories ?? []).map((c) => (
              <NavLink
                key={c.id}
                label={c.name}
                pl={12 + 14 * (c.path.split(' / ').length - 1)}
                rightSection={
                  <Text size="xs" c="dimmed">
                    {c.articles || ''}
                  </Text>
                }
                active={f.category === String(c.id)}
                onClick={() => setF({ category: String(c.id) })}
              />
            ))}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 9 }}>
          <Group mb="sm" gap="sm" align="flex-start">
            <SearchInput value={f.q} onChange={(q) => setF({ q })} placeholder="Search titles, tags and text…" />
            <Select
              w={160}
              aria-label="Tag"
              placeholder="Any tag"
              clearable
              searchable
              value={f.tag || null}
              onChange={(tag) => setF({ tag: tag ?? '' })}
              data={(tags ?? []).map((t) => t.tag)}
            />
            <Select w={140} aria-label="Status" placeholder="Any status" clearable value={f.status || null} onChange={(status) => setF({ status: status ?? '' })} data={ARTICLE_STATUSES} />
            <Select
              w={150}
              aria-label="Visibility"
              placeholder="Any visibility"
              clearable
              value={f.visibility || null}
              onChange={(visibility) => setF({ visibility: visibility ?? '' })}
              data={ARTICLE_VISIBILITIES}
            />
            {isFetching && <Loader size="xs" mt={10} />}
          </Group>
          <Stack gap="xs">
            {data?.items.length === 0 && (
              <Text c="dimmed" size="sm">
                {f.q ? 'Nothing found. Try fewer or other words.' : 'No articles yet. Write down what you will need again: how-tos, settings, notes about clients.'}
              </Text>
            )}
            {data?.items.map((a) => <ArticleCard key={a.id} article={a} terms={terms} />)}
          </Stack>
          {data && data.total > LIMIT && (
            <Pagination
              mt="md"
              total={Math.ceil(data.total / LIMIT)}
              value={Math.floor(Number(f.offset) / LIMIT) + 1}
              onChange={(page) => setF({ offset: String((page - 1) * LIMIT) })}
            />
          )}
        </Grid.Col>
      </Grid>
    </>
  )
}

function ArticleCard({ article, terms }: { article: ArticleSummary; terms: string[] }) {
  return (
    <Card withBorder padding="sm">
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <Stack gap={2}>
          <Anchor component={Link} to={`/kb/${article.id}`} fw={600}>
            {article.title}
          </Anchor>
          <Text size="xs" c="dimmed">
            {[article.category_path, article.party_name].filter(Boolean).join(' · ') || 'No category'}
            {' · updated '}
            <DateText value={article.updated_at.slice(0, 10)} />
          </Text>
        </Stack>
        <ArticleBadges article={article} />
      </Group>
      {article.snippet && (
        <Highlight highlight={terms} size="sm" mt={6} c="dimmed">
          {article.snippet}
        </Highlight>
      )}
      {article.tags.length > 0 && (
        <Group gap={4} mt={6}>
          {article.tags.map((t) => (
            <Badge key={t} size="xs" variant="outline" color="gray">
              {t}
            </Badge>
          ))}
        </Group>
      )}
    </Card>
  )
}

// -- one article --------------------------------------------------------------------------------

function useArticle(articleId: number) {
  return useQuery({
    queryKey: ['kb-article', articleId],
    queryFn: async () => unwrap(await api.GET('/api/kb/articles/{article_id}', { params: { path: { article_id: articleId } } })),
  })
}

function Files({ article, onInsert }: { article: Article; onInsert?: (markdown: string) => void }) {
  const queryClient = useQueryClient()
  const { canEdit } = useAuth()
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return (await send('POST', `/api/kb/articles/${article.id}/attachments`, form)) as Article
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(['kb-article', article.id], saved)
      const added = saved.attachments[saved.attachments.length - 1]
      if (added && onInsert) onInsert(reference(added))
      notifySaved('File attached')
    },
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async (id: number) =>
      unwrap(
        await api.DELETE('/api/kb/articles/{article_id}/attachments/{attachment_id}', {
          params: { path: { article_id: article.id, attachment_id: id } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['kb-article', article.id] }),
    onError: notifyError,
  })
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Text fw={600}>Files</Text>
        {canEdit && onInsert && (
          <FileButton onChange={(file) => file && upload.mutate(file)}>
            {(props) => (
              <Button {...props} size="xs" variant="light" leftSection={<IconPaperclip size={14} />} loading={upload.isPending}>
                Attach a file
              </Button>
            )}
          </FileButton>
        )}
      </Group>
      {article.attachments.length === 0 ? (
        <Text size="sm" c="dimmed">
          {onInsert ? 'Images and files attached here can be shown or linked in the text.' : 'No files.'}
        </Text>
      ) : (
        <Table>
          <Table.Tbody>
            {article.attachments.map((a) => (
              <Table.Tr key={a.id}>
                <Table.Td>
                  <Anchor href={a.url} target="_blank" size="sm">
                    {a.name}
                  </Anchor>
                </Table.Td>
                <Table.Td>
                  <Text size="xs" c="dimmed">
                    {a.size < 1024 ? `${a.size} bytes` : `${Math.round(a.size / 1024)} KB`}
                  </Text>
                </Table.Td>
                {onInsert && (
                  <Table.Td w={1}>
                    <Group gap={4} wrap="nowrap">
                      <Button size="compact-xs" variant="subtle" onClick={() => onInsert(reference(a))}>
                        Insert
                      </Button>
                      <ActionIcon variant="subtle" color="red" aria-label={`Remove ${a.name}`} onClick={() => remove.mutate(a.id)}>
                        <IconTrash size={14} />
                      </ActionIcon>
                    </Group>
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Card>
  )
}

/** How the text shows an attached file: an image in place, anything else as a link. */
function reference(file: Article['attachments'][number]) {
  const name = file.name.replace(/[[\]]/g, '')
  return file.content_type.startsWith('image/') ? `![${name}](${file.url})` : `[${name}](${file.url})`
}

function Versions({ article }: { article: Article }) {
  const queryClient = useQueryClient()
  const { canEdit } = useAuth()
  const [open, setOpen] = useState<number | null>(null)
  const path = { article_id: article.id }
  const { data } = useQuery({
    queryKey: ['kb-versions', article.id, article.version],
    queryFn: async () => unwrap(await api.GET('/api/kb/articles/{article_id}/versions', { params: { path } })),
  })
  const { data: shown } = useQuery({
    queryKey: ['kb-version', article.id, open],
    queryFn: async () =>
      unwrap(await api.GET('/api/kb/articles/{article_id}/versions/{version}', { params: { path: { ...path, version: open ?? 0 } } })),
    enabled: open !== null,
  })
  const restore = useMutation({
    mutationFn: async () => {
      if (!shown) throw new Error('No version')
      return unwrap(
        await api.PATCH('/api/kb/articles/{article_id}', {
          params: { path },
          body: { title: shown.title, tags: shown.tags, body: shown.body, base_version: article.version },
        }),
      )
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(['kb-article', article.id], saved)
      queryClient.invalidateQueries({ queryKey: ['kb-articles'] })
      notifySaved(`Version ${shown?.version} restored as version ${saved.version}`)
      setOpen(null)
    },
    onError: notifyError,
  })
  return (
    <>
      <DataTable
        rows={data}
        rowKey={(v) => v.version}
        onRowClick={(v) => setOpen(v.version)}
        empty="No versions."
        columns={[
          { key: 'v', header: 'Version', render: (v) => (v.version === article.version ? `${v.version} (current)` : v.version) },
          { key: 'title', header: 'Title', wide: true, render: (v) => v.title },
          { key: 'by', header: 'Saved by', render: (v) => v.saved_by },
          { key: 'at', header: 'Saved', render: (v) => <SavedAt value={v.saved_at} /> },
        ]}
      />
      <Modal opened={open !== null} onClose={() => setOpen(null)} size="xl" title={shown ? `Version ${shown.version}: ${shown.title}` : 'Version'}>
        {shown ? (
          <Stack>
            <Text size="xs" c="dimmed">
              Saved by {shown.saved_by ?? 'unknown'}, <SavedAt value={shown.saved_at} />
              {shown.tags.length > 0 && ` · tags: ${shown.tags.join(', ')}`}
            </Text>
            <Markdown text={shown.body} />
            {canEdit && shown.version !== article.version && (
              <Group justify="flex-end">
                <Button variant="light" loading={restore.isPending} onClick={() => restore.mutate()}>
                  Restore this version
                </Button>
              </Group>
            )}
          </Stack>
        ) : (
          <Loader size="sm" />
        )}
      </Modal>
    </>
  )
}

function SavedAt({ value }: { value: string }) {
  const { locale } = useAuth()
  return <>{formatDateTime(value, locale.locale)}</>
}

export function ArticlePage() {
  const { id } = useParams()
  const articleId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { canEdit, isOwner } = useAuth()
  const { data: article, error } = useArticle(articleId)
  const remove = useMutation({
    mutationFn: async () => unwrap(await api.DELETE('/api/kb/articles/{article_id}', { params: { path: { article_id: articleId } } })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kb-articles'] })
      queryClient.invalidateQueries({ queryKey: ['kb-categories'] })
      notifySaved('Article deleted')
      navigate('/kb')
    },
    onError: notifyError,
  })
  if (error) return <Text c="red">{error.message}</Text>
  if (!article) return <Loader />
  const sendable = article.visibility === 'shareable' && article.status === 'published'
  return (
    <>
      <PageHeader
        title={
          <Group gap="sm">
            {article.title}
            <ArticleBadges article={article} />
          </Group>
        }
        subtitle={[article.category_path, article.party_name].filter(Boolean).join(' · ')}
        actions={
          <>
            {canEdit && (
              <Button component={Link} to={`/kb/${article.id}/edit`} leftSection={<IconEdit size={16} />}>
                Edit
              </Button>
            )}
            <PdfButton href={`/api/kb/articles/${article.id}/pdf`} />
            {canEdit &&
              (sendable ? (
                <ArticleEmailButton articleId={article.id} pdfName={fileName(article.title)} />
              ) : (
                <Tooltip label={article.visibility === 'internal' ? 'Internal articles cannot be sent' : 'Publish it to send it'}>
                  <Button variant="default" disabled>
                    Email to…
                  </Button>
                </Tooltip>
              ))}
            {isOwner && (
              <Button
                variant="subtle"
                color="red"
                leftSection={<IconTrash size={16} />}
                onClick={() =>
                  modals.openConfirmModal({
                    title: `Delete "${article.title}"?`,
                    children: <Text size="sm">The article, all its versions and its files are deleted.</Text>,
                    labels: { confirm: 'Delete', cancel: 'Cancel' },
                    confirmProps: { color: 'red' },
                    onConfirm: () => remove.mutate(),
                  })
                }
              >
                Delete
              </Button>
            )}
          </>
        }
      />
      <Tabs defaultValue="article" keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="article">Article</Tabs.Tab>
          <Tabs.Tab value="versions">Versions ({article.version})</Tabs.Tab>
          <Tabs.Tab value="history">History</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="article">
          <Grid>
            <Grid.Col span={{ base: 12, md: 9 }}>
              <Card withBorder>
                {article.body.trim() ? <Markdown text={article.body} /> : <Text c="dimmed">No text yet.</Text>}
              </Card>
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 3 }}>
              <Stack>
                <Card withBorder>
                  <Stack gap={6}>
                    {article.party_id && (
                      <Text size="sm">
                        About{' '}
                        <Anchor component={Link} to={`/contacts/${article.party_id}`}>
                          {article.party_name}
                        </Anchor>
                      </Text>
                    )}
                    {article.tags.length > 0 && (
                      <Group gap={4}>
                        {article.tags.map((t) => (
                          <Badge key={t} size="sm" variant="outline" color="gray" component={Link} to={`/kb?tag=${encodeURIComponent(t)}`} style={{ cursor: 'pointer' }}>
                            {t}
                          </Badge>
                        ))}
                      </Group>
                    )}
                    <Text size="xs" c="dimmed">
                      Version {article.version}, saved by {article.updated_by ?? 'unknown'} <SavedAt value={article.updated_at} />
                    </Text>
                    <Text size="xs" c="dimmed">
                      Written by {article.created_by ?? 'unknown'} <SavedAt value={article.created_at} />
                    </Text>
                  </Stack>
                </Card>
                {article.attachments.length > 0 && <Files article={article} />}
              </Stack>
            </Grid.Col>
          </Grid>
        </Tabs.Panel>
        <Tabs.Panel value="versions">
          <Versions article={article} />
        </Tabs.Panel>
        <Tabs.Panel value="history">
          <HistoryPanel entityType="kb_article" entityId={article.id} />
        </Tabs.Panel>
      </Tabs>
    </>
  )
}

// -- writing ------------------------------------------------------------------------------------

type Edit = (text: string, start: number, end: number) => { text: string; start: number; end: number }

/** Wrap the selection (or a placeholder) in markers: **bold**. */
const wrap =
  (before: string, after: string, placeholder: string): Edit =>
  (text, start, end) => {
    const inner = text.slice(start, end) || placeholder
    return {
      text: text.slice(0, start) + before + inner + after + text.slice(end),
      start: start + before.length,
      end: start + before.length + inner.length,
    }
  }

/** Put a prefix before every selected line: "- " for a list. */
const prefixLines =
  (prefix: (n: number) => string): Edit =>
  (text, start, end) => {
    const lineStart = text.lastIndexOf('\n', start - 1) + 1
    const lines = text.slice(lineStart, end).split('\n')
    const changed = lines.map((line, i) => prefix(i + 1) + line).join('\n')
    return { text: text.slice(0, lineStart) + changed + text.slice(end), start: lineStart, end: lineStart + changed.length }
  }

/** Insert a block on lines of its own. */
const block =
  (snippet: string): Edit =>
  (text, start) => {
    const before = start === 0 || text[start - 1] === '\n' ? '' : '\n'
    const insert = `${before}\n${snippet}\n`
    return { text: text.slice(0, start) + insert + text.slice(start), start: start + insert.length, end: start + insert.length }
  }

const TOOLS: { label: string; icon: typeof IconBold; edit: Edit }[] = [
  { label: 'Heading', icon: IconH2, edit: prefixLines(() => '## ') },
  { label: 'Bold', icon: IconBold, edit: wrap('**', '**', 'bold text') },
  { label: 'Italic', icon: IconItalic, edit: wrap('_', '_', 'text') },
  { label: 'List', icon: IconList, edit: prefixLines(() => '- ') },
  { label: 'Numbered list', icon: IconListNumbers, edit: prefixLines((n) => `${n}. `) },
  { label: 'Link', icon: IconLink, edit: wrap('[', '](https://)', 'link text') },
  { label: 'Code', icon: IconCode, edit: wrap('\n```\n', '\n```\n', 'command or setting') },
  { label: 'Table', icon: IconTable, edit: block('| Column | Column |\n|---|---|\n| | |') },
]

function ArticleForm({ article }: { article?: Article }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [params] = useSearchParams()
  const { data: categories } = useKbCategories()
  const { data: tags } = useKbTags()
  const editor = useRef<HTMLTextAreaElement>(null)
  // Whether the cursor was put somewhere; until then, buttons and files add at the end.
  const placed = useRef(false)
  const [v, setV] = useState({
    title: article?.title ?? '',
    category_id: article?.category_id ? String(article.category_id) : params.get('category'),
    tags: article?.tags ?? [],
    status: article?.status ?? 'draft',
    visibility: article?.visibility ?? 'internal',
    party_id: article?.party_id ?? (params.get('contact') ? Number(params.get('contact')) : null),
  })
  const [body, setBody] = useState(article?.body ?? '')
  const set = (change: Partial<typeof v>) => setV((old) => ({ ...old, ...change }))

  const apply = (edit: Edit) => {
    const area = editor.current
    const start = area && placed.current ? area.selectionStart : body.length
    const end = area && placed.current ? area.selectionEnd : body.length
    const result = edit(body, start, end)
    setBody(result.text)
    placed.current = true
    requestAnimationFrame(() => {
      area?.focus()
      area?.setSelectionRange(result.start, result.end)
    })
  }
  const insert = (markdown: string) => apply(block(markdown))

  const save = useMutation({
    mutationFn: async () => {
      const fields = {
        title: v.title.trim(),
        category_id: v.category_id ? Number(v.category_id) : null,
        tags: v.tags,
        body,
        status: v.status as Article['status'],
        visibility: v.visibility as Article['visibility'],
        party_id: v.party_id,
      }
      return article
        ? unwrap(
            await api.PATCH('/api/kb/articles/{article_id}', {
              params: { path: { article_id: article.id } },
              body: { ...fields, base_version: article.version },
            }),
          )
        : unwrap(await api.POST('/api/kb/articles', { body: fields }))
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(['kb-article', saved.id], saved)
      queryClient.invalidateQueries({ queryKey: ['kb-articles'] })
      queryClient.invalidateQueries({ queryKey: ['kb-categories'] })
      queryClient.invalidateQueries({ queryKey: ['kb-tags'] })
      notifySaved(article ? `Saved as version ${saved.version}` : 'Article saved')
      navigate(article ? `/kb/${saved.id}` : `/kb/${saved.id}/edit`, { replace: true })
    },
    onError: notifyError,
  })
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate()
      }}
    >
      <Stack>
        <Card withBorder>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <TextInput label="Title" required value={v.title} onChange={(e) => set({ title: e.currentTarget.value })} style={{ gridColumn: 'span 2' }} />
            <Select label="Category" clearable searchable data={categoryOptions(categories)} value={v.category_id} onChange={(category_id) => set({ category_id })} />
            <TagsInput label="Tags" data={(tags ?? []).map((t) => t.tag)} value={v.tags} onChange={(t) => set({ tags: t })} placeholder="Type and press Enter" splitChars={[',']} />
            <ContactSelect label="About a contact" placeholder="None" clearable value={v.party_id} onChange={(party_id) => set({ party_id })} />
            <Group gap="md" align="flex-end">
              <SegmentedControl data={ARTICLE_STATUSES} value={v.status} onChange={(status) => set({ status: status as Article['status'] })} aria-label="Status" />
              <SegmentedControl
                data={ARTICLE_VISIBILITIES}
                value={v.visibility}
                onChange={(visibility) => set({ visibility: visibility as Article['visibility'] })}
                aria-label="Visibility"
              />
            </Group>
          </SimpleGrid>
          <Text size="xs" c="dimmed" mt="xs">
            Internal articles are only for you and your staff; shareable ones, once published, can be emailed to clients.
          </Text>
        </Card>
        <Card withBorder>
          <Group gap={4} mb="xs">
            {TOOLS.map((tool) => (
              <Tooltip key={tool.label} label={tool.label}>
                <ActionIcon variant="default" aria-label={tool.label} onClick={() => apply(tool.edit)}>
                  <tool.icon size={16} />
                </ActionIcon>
              </Tooltip>
            ))}
            {!article && (
              <Text size="xs" c="dimmed" ml="sm">
                <IconPhoto size={12} /> Save the article first to attach images and files.
              </Text>
            )}
          </Group>
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <Textarea
              ref={editor}
              onFocus={() => (placed.current = true)}
              aria-label="Text"
              autosize
              minRows={18}
              maxRows={40}
              value={body}
              onChange={(e) => setBody(e.currentTarget.value)}
              styles={{ input: { fontFamily: 'var(--mantine-font-family-monospace)', fontSize: 13 } }}
              placeholder={'Markdown: ## for a heading, - for a list, **bold**, `code`…'}
            />
            <Card withBorder bg="var(--mantine-color-body)" style={{ overflow: 'auto' }} aria-label="Preview">
              {body.trim() ? <Markdown text={body} /> : <Text c="dimmed" size="sm">The preview shows here.</Text>}
            </Card>
          </SimpleGrid>
        </Card>
        {article && <Files article={article} onInsert={insert} />}
        <Group justify="flex-end">
          <Button variant="default" onClick={() => navigate(article ? `/kb/${article.id}` : '/kb')}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending} disabled={!v.title.trim()}>
            {article ? 'Save' : 'Save article'}
          </Button>
        </Group>
      </Stack>
    </form>
  )
}

export function NewArticlePage() {
  return (
    <>
      <PageHeader title="New article" />
      <ArticleForm />
    </>
  )
}

export function EditArticlePage() {
  const { id } = useParams()
  const { data: article, error } = useArticle(Number(id))
  if (error) return <Text c="red">{error.message}</Text>
  if (!article) return <Loader />
  return (
    <>
      <PageHeader title={`Edit: ${article.title}`} subtitle={`Version ${article.version}`} />
      {/* A new form when someone else's save arrives (the version changes). */}
      <ArticleForm key={article.version} article={article} />
    </>
  )
}

/** A contact's Articles tab: what the knowledge base says about them. */
export function ContactArticles({ partyId }: { partyId: number }) {
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const { data } = useQuery({
    queryKey: ['kb-articles', { party: partyId }],
    queryFn: async () => unwrap(await api.GET('/api/kb/articles', { params: { query: { party_id: partyId, limit: 200 } } })).items,
  })
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Text fw={600}>Knowledge base</Text>
        {canEdit && (
          <Button component={Link} to={`/kb/new?contact=${partyId}`} size="xs" variant="light" leftSection={<IconPlus size={14} />}>
            New article
          </Button>
        )}
      </Group>
      <DataTable<ArticleSummary>
        rows={data}
        rowKey={(r) => r.id}
        onRowClick={(r) => navigate(`/kb/${r.id}`)}
        empty="No articles about this contact."
        columns={[
          { key: 'title', header: 'Title', wide: true, render: (r) => r.title },
          { key: 'cat', header: 'Category', render: (r) => r.category_path },
          { key: 'updated', header: 'Updated', render: (r) => <DateText value={r.updated_at.slice(0, 10)} /> },
          { key: 'badges', header: '', render: (r) => <ArticleBadges article={r} /> },
        ]}
      />
    </Card>
  )
}
