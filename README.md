# Documentation Scraper

A robust, asynchronous Python tool for scraping and cleaning documentation from any website. It recursively traverses documentation sites, extracts and cleans text using an LLM, and outputs the results in Markdown format. Includes rate limiting, logging, and error handling for reliability.

---

## Features

- Asynchronous crawling with concurrency and rate limiting
- LLM-powered cleaning of extracted content (OpenAI API)
- Recursive traversal of all subpages within the same domain
- Custom logging per target domain
- Robust retry and error handling (network, LLM, HTTP errors)
- Output in clean, Markdown-formatted text
- Easily configurable for different documentation sites

---

## Requirements

- Python 3.10+
- [UV](https://github.com/astral-sh/uv) (recommended for fast dependency management)
- `pyproject.toml` (all dependencies are managed here)
- `httpx` (async HTTP client)
- `beautifulsoup4` (HTML parsing)
- `openai` (OpenAI API client)
- `aiofiles` (async file I/O)
- `python-dotenv` (environment variable management)
- `lxml` (parser for BeautifulSoup)

Install all dependencies with:

```bash
make install
```

Or, directly:

```bash
uv sync
```

---

## Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd doc-scrape
   ```

2. **Install dependencies:**
   ```bash
   make install
   # or
   uv sync
   ```

3. **Set up your environment variables in a `.env` file:**
   ```
   OPENAI_API_KEY=your_openai_api_key
   ```

---

## Usage

You can use the Makefile for common tasks:

- **Run the scraper:**
  ```bash
  make run BASE_URL=https://example.com/docs OUTPUT=example_docs.txt
  ```
  - `BASE_URL` (required): The base URL of the documentation website to scrape
  - `OUTPUT` (optional): Output file name (default: `docs_output.txt`)

- **Add a new dependency:**
  ```bash
  make add NAME=package_name
  ```
  This will add the package to `pyproject.toml` using `uv add`.

- **Manual install (if needed):**
  ```bash
  uv sync
  ```

- **Install the project as a package (for editable mode):**
  ```bash
  uv pip install .
  ```

- **Clean up build artifacts:**
  ```bash
  make clean
  ```

---

## Output

- Each page's cleaned content is written to the output file in Markdown format.
- The URL of each page is included as a header.
- Separator lines (`====================`) are used between pages.
- A log file is generated per domain (e.g., `docs_example_com_scraping.log`).

---

## Advanced Configuration

- **Concurrency and rate limits** can be adjusted in `scrape.py` via `MAX_CONCURRENT_REQUESTS` and `REQUESTS_PER_MINUTE`.
- **System prompt** for the LLM can be customized in `scrape.py`.
- **Error handling**: The script will stop after 18 consecutive LLM failures.

---

## Troubleshooting

- If you hit OpenAI rate limits, lower concurrency or increase delay.
- For network errors, the script retries with exponential backoff.
- For memory issues, reduce the number of concurrent requests.
- Check the generated log file for detailed error messages.

---

## License

This project is licensed under the **PolyForm Internal Use License 1.0.0**.

- You may use, modify, and create new works based on this software **for internal business purposes only**.
- **Distribution is not permitted.**
- No warranty is provided; use at your own risk.
- For full terms, see the [LICENCE](./LICENCE) file or [PolyForm Internal Use License 1.0.0](https://polyformproject.org/licenses/internal-use/1.0.0).

--- 