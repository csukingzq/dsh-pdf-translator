"""Map BabelDOC progress events onto the panel's phases.

The engine reports ``progress_start``/``progress_update``/``progress_end``
events with a stage name and an overall percentage. Only this module knows
which stage belongs to which phase, so the UI stays independent of the engine.
"""
import time

PHASES = ('preparing', 'analyzing', 'glossary', 'translating', 'typesetting', 'exporting', 'completed')

# Stage names come from BabelDOC's pipeline (plus the wrapper's own stages).
STAGE_PHASES = {
    'detectscannedfile': 'analyzing',
    'layoutparser': 'analyzing',
    'tableparser': 'analyzing',
    'paragraphfinder': 'analyzing',
    'stylesandformulas': 'analyzing',
    'automatictermextractor': 'glossary',
    'iltranslator': 'translating',
    'typesetting': 'typesetting',
}

PROGRESS_TYPES = {'progress_start', 'progress_update', 'progress_end'}


def phase_for(stage):
    key = ''.join(ch for ch in str(stage or '').lower() if ch.isalnum())
    if key in STAGE_PHASES:
        return STAGE_PHASES[key]
    if 'translat' in key:
        return 'translating'
    if 'term' in key:
        return 'glossary'
    if 'typeset' in key:
        return 'typesetting'
    if 'layout' in key or 'parag' in key or 'formula' in key or 'table' in key:
        return 'analyzing'
    return 'analyzing'


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def map_event(event, state=None):
    """Normalize one engine event. Returns a dict for the panel.

    ``percent`` never goes backwards; a stage that restarts (e.g. a retried
    chunk) cannot make the progress bar jump back. ``completed``/``total``
    describe the current stage, which is what the panel counts.
    """
    state = dict(state or {})
    stage = event.get('stage') or state.get('stage') or ''
    phase = phase_for(stage) if stage else state.get('phase') or 'preparing'
    if event.get('type') == 'progress_start' and phase == 'preparing':
        phase = phase_for(stage)
    if phase not in PHASES:
        phase = 'analyzing'

    total = _number(event.get('stage_total'))
    completed = _number(event.get('stage_current'))
    if completed is None:
        completed = state.get('completed') or 0
    if total is None:
        total = state.get('total') or 0
    completed = max(0, int(completed))
    total = max(completed, int(total))

    percent = _number(event.get('overall_progress'))
    if percent is None:
        percent = state.get('percent') or 0
    percent = max(0.0, min(100.0, float(percent)))
    percent = max(percent, float(state.get('percent') or 0))
    if phase == 'completed':
        percent = 100.0
    if event.get('type') == 'progress_end' and phase == 'typesetting':
        percent = max(percent, 99.0)

    return {
        'phase': phase,
        'stage': str(stage)[:60],
        'percent': int(round(percent)),
        'completed': completed,
        'total': total,
        'elapsedSeconds': round(state.get('elapsedSeconds') or 0, 1),
    }


def completed(state):
    return {**dict(state or {}), 'phase': 'completed', 'percent': 100, 'stage': ''}


def preparing(total=0):
    return {'phase': 'preparing', 'stage': '', 'percent': 0, 'completed': 0, 'total': max(0, int(total or 0)), 'elapsedSeconds': 0.0}
