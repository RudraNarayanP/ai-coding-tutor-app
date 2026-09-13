import React, { Component, ErrorInfo, ReactNode } from 'react'

interface Props {
  children?: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Unhandled React Error:', error, errorInfo)
  }

  public handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div
          role="alert"
          style={{
            padding: '40px 24px',
            maxWidth: '600px',
            margin: '60px auto',
            textAlign: 'center',
            borderRadius: '16px',
            border: '2px solid #f87171',
            background: '#fef2f2',
            color: '#991b1b',
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>⚠️</div>
          <h1 style={{ fontSize: '24px', fontWeight: 900, marginBottom: '12px' }}>
            Something went wrong
          </h1>
          <p style={{ fontSize: '15px', fontWeight: 600, marginBottom: '20px', color: '#7f1d1d' }}>
            {this.state.error?.message || 'An unexpected error occurred in Patchwork Tutor.'}
          </p>
          <button
            onClick={this.handleReset}
            style={{
              padding: '12px 24px',
              fontSize: '15px',
              fontWeight: 800,
              borderRadius: '12px',
              border: 'none',
              background: '#dc2626',
              color: '#ffffff',
              cursor: 'pointer',
              boxShadow: '0 4px 0 #991b1b',
            }}
          >
            Try Again 🔄
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
