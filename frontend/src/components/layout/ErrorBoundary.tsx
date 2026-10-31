import { Component, type ErrorInfo, type ReactNode } from 'react'
import { translate } from '@/i18n'
import { logClientError } from '@/lib/clientLog'
import { LoadError } from './LoadError'

/** A component that throws while drawing shows the error (and goes to the log) instead of a blank window. `resetKey`:
 * a new value (another page) tries again. */
export class ErrorBoundary extends Component<
  { children: ReactNode; resetKey?: string; page?: boolean },
  { error: unknown; key?: string }
> {
  state: { error: unknown; key?: string } = { error: null }

  static getDerivedStateFromError(error: unknown) {
    return { error }
  }

  static getDerivedStateFromProps(props: { resetKey?: string }, state: { error: unknown; key?: string }) {
    if (props.resetKey === state.key) return null
    return { error: null, key: props.resetKey }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    logClientError('render', error, info.componentStack ?? undefined)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <LoadError
        error={this.state.error}
        title={translate('app.renderFailed')}
        page={this.props.page}
        onRetry={() => this.setState({ error: null })}
      />
    )
  }
}
