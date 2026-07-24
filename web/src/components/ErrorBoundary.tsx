import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("OneChoice UI error", error, info.componentStack);
  }

  private retry = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      return (
        <section className="oc-page oc-error-card" role="alert">
          <h1 className="oc-page-title">Något gick snett</h1>
          <p className="oc-page-sub">
            Vi kunde inte visa den här sidan. Prova igen — dina sparade val
            ligger kvar.
          </p>
          <button type="button" className="oc-cta" onClick={this.retry}>
            Försök igen
          </button>
          <button
            type="button"
            className="oc-btn oc-btn-ghost"
            onClick={() => {
              window.location.href = "/";
            }}
          >
            Till Hem
          </button>
        </section>
      );
    }
    return this.props.children;
  }
}
