import { InlineNotification } from '@carbon/react'

export default function ErrorNotice({
  message,
  title = 'Could not load the workspace',
}: {
  message: string
  title?: string
}) {
  return (
    <InlineNotification
      className="page-notification"
      kind="error"
      title={title}
      subtitle={message}
      hideCloseButton
      lowContrast
    />
  )
}
