import os

import pandas as pd
import requests
from rich.console import Console

console = Console()


def build_dataframe(rows):
    # pandas is only used inside deferred code, so this is a lazy-import candidate.
    return pd.DataFrame(rows)


def fetch_url(url):
    # requests is used, so it should not be marked unused.
    return requests.get(url, timeout=10).text


def main():
    console.print(os.getcwd())
