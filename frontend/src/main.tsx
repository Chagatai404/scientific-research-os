import {createRoot} from 'react-dom/client';
import {Component, type ReactNode} from 'react';
import {App} from './App';
import 'katex/dist/katex.min.css';
import './style.css';
import './dark.css';

class ErrorBoundary extends Component<{children: ReactNode}, {error: string}> {
  state = {error: ''};
  static getDerivedStateFromError(error: Error) {return {error: error.message};}
  render() {return this.state.error ? <main className="fallback"><h1>The workspace encountered a problem</h1><p>{this.state.error}</p><a href="/">Open the original portal</a><button onClick={() => location.reload()}>Reload</button></main> : this.props.children;}
}
createRoot(document.getElementById('root')!).render(<ErrorBoundary><App /></ErrorBoundary>);
