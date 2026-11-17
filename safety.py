"""Small safety helpers. Plain Python (no Streamlit), so tests.py can check them directly."""

import re
import threading
import time

# Characters that mean something in Markdown (and "$", which Streamlit uses for maths).
_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+!|<>~$])")


def safe(text):
    """Text from a resume or from the AI, shown as plain text. Without this, text such as
    '![x](http://...)' or '<b>' would be drawn as a picture or formatting instead of shown as written."""
    return _MARKDOWN.sub(r"\\\1", str(text))


class DailyAllowance:
    """Counts live runs for the whole app per day, so visitors cannot use up the free Groq allowance.
    It holds numbers only, never anyone's data, so it is safe to share between visitors."""

    def __init__(self, per_day):
        self.per_day, self.day, self.used = per_day, None, 0
        self.lock = threading.Lock()  # two visitors at the same moment cannot both take the last run

    def take(self, now=None):
        """Uses one run, and returns True if there was one left today."""
        day = time.strftime("%Y%m%d", time.localtime(now))
        with self.lock:
            if day != self.day:
                self.day, self.used = day, 0
            if self.used >= self.per_day:
                return False
            self.used += 1
            return True

    def left(self, now=None):
        day = time.strftime("%Y%m%d", time.localtime(now))
        return self.per_day if day != self.day else self.per_day - self.used
