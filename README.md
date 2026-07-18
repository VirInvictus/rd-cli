# rd-cli

A simple CLI client for Raindrop.io.

## Setup

```bash
uv pip install -e .
```

Make sure your token is in `.env`:
```
RAINDROP_TEST_TOKEN=your-token-here
```

## Usage

```bash
rd list
rd list -s "query"
rd add "https://example.com" -t "My Title" --tags read-later AI
rd edit 12345 -t "New Title" --tags new tag
rd rm 12345
```
