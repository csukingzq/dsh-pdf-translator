"""Console progress display for AI translation and LaTeX compilation."""
import sys
import threading
import time

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - minimal console fallback
    tqdm = None


class _Line:
    """Single reusable status line for the spinner (no tqdm bar active)."""
    def __init__(self):
        self._width = 0
        self._lock = threading.Lock()

    def show(self, text):
        with self._lock:
            pad = ' ' * max(0, self._width - len(text))
            sys.stdout.write('\r' + text + pad)
            sys.stdout.flush()
            self._width = len(text)

    def clear(self):
        with self._lock:
            if self._width:
                sys.stdout.write('\r' + ' ' * self._width + '\r')
                sys.stdout.flush()
                self._width = 0


_line = _Line()


class Spinner:
    """Show elapsed time while one blocking step runs (project build, compile)."""
    def __init__(self, description, interval=0.3):
        self.description = description
        self.interval = interval
        self.enabled = sys.stdout.isatty()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._started = time.monotonic()

    def _run(self):
        frames = '|/-\\'
        index = 0
        while not self._stop.wait(self.interval):
            _line.show(f'{self.description} {frames[index % 4]} {int(time.monotonic()-self._started)}s')
            index += 1

    def __enter__(self):
        if self.enabled:
            self._thread.start()
        return self

    def __exit__(self, *exc):
        if self.enabled:
            self._stop.set()
            self._thread.join()
            _line.clear()
        return False


def spinner(description, interval=0.3):
    """Convenience wrapper used by the renderer."""
    return Spinner(description, interval)


def write(message):
    """Print a line without breaking an active tqdm bar."""
    if tqdm is not None:
        tqdm.write(message, file=sys.stdout)
    else:
        print(message, flush=True)


def bar(total, description, unit='项', bar_format=None, position=None):
    """Progress bar; disabled automatically when stdout is not a terminal."""
    if tqdm is None:
        return _Fallback(total, description, unit)
    return tqdm(total=total, desc=description, unit=unit, file=sys.stdout,
                dynamic_ncols=True, leave=True, mininterval=0.3, disable=None,
                position=position, bar_format=bar_format)


class _Fallback:
    """Print at most ten progress lines when tqdm is unavailable."""
    def __init__(self, total, description, unit):
        self.total = max(1, total)
        self.description = description
        self.unit = unit
        self.n = 0
        self.step = max(1, self.total // 10)

    def update(self, n=1):
        self.n += n
        if self.n >= self.total or self.n % self.step == 0:
            print(f'{self.description} {self.n}/{self.total} {self.unit}', flush=True)

    def refresh(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
