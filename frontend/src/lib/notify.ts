import { notifications } from '@mantine/notifications'

export function notifyError(error: unknown) {
  notifications.show({
    color: 'red',
    title: 'Something went wrong',
    message: error instanceof Error ? error.message : String(error),
    autoClose: 8000,
  })
}

export function notifySaved(message = 'Saved') {
  notifications.show({ color: 'green', message, autoClose: 2500 })
}
