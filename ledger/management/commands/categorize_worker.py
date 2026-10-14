import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from ledger.ollama import OllamaSuggester
from ledger.suggestions import backoff, run_once

# Seconds between looks for new work while there is none.
IDLE_POLL = 10


class Command(BaseCommand):
    help = (
        "Suggest Subcategories for unresolved Transactions with the local Ollama, in a loop. "
        "Runs as its own Compose service; retries with backoff while Ollama is unreachable."
    )

    def handle(self, *args, **options):
        suggester = OllamaSuggester(settings.OLLAMA_URL)
        self.stdout.write(
            f"Suggesting with {suggester.model} at {settings.OLLAMA_URL or '(unset)'}."
        )
        failures = 0
        while True:
            close_old_connections()
            run = run_once(suggester)
            if run.error:
                failures += 1
                delay = backoff(failures)
                self.stderr.write(f"Suggestions unavailable, retrying in {delay}s: {run.error}")
                time.sleep(delay)
                continue
            if failures:
                self.stdout.write("Suggestions available again.")
            failures = 0
            if run.asked:
                self.stdout.write(f"Asked about {run.asked} Transactions.")
            else:
                time.sleep(IDLE_POLL)
