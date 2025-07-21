# Coda Documentation Scraper

A specialized scraper for extracting and cleaning documentation from Coda.io pages.

## Features

- Asynchronous crawling using the Spider Cloud SDK
- Content extraction and transformation to Markdown
- LLM-powered cleaning of scraped content to remove noise
- Recursive traversal of linked pages within the same domain
- Rate limiting to avoid overloading servers

## Requirements

- Python 3.10+
- `spider-client`: Spider Cloud's official Python SDK
- `openai`: OpenAI API client for content cleaning
- `aiofiles`: For asynchronous file I/O
- `python-dotenv`: For environment variable management

## Setup

1. Clone the repository
   ```bash
   git clone <repository-url>
   cd doc-scrape
   ```

2. Install the dependencies
   ```bash
   pip install -r requirements.txt
   ```
   
   Or if you're using Poetry:
   ```bash
   poetry install
   ```

3. Set up your environment variables in a `.env` file:
   ```
   SPIDER_API_KEY=your_spider_cloud_api_key
   OPENAI_API_KEY=your_openai_api_key
   ```

## Usage

### Option 1: Run the helper script

The simplest way to run the scraper on the PlanYear Client Knowledge Base:

```bash
python run_scraper.py
```

### Option 2: Run the scraper directly

You can also run the enhanced scraper directly with custom arguments:

```bash
python enhanced_scraper.py https://coda.io/d/PlanYear-Client-Knowledge-Base_dSbXPwSgGqG --output my_output.md
```

Or if you want to provide your API key as an argument:

```bash
python enhanced_scraper.py https://coda.io/d/PlanYear-Client-Knowledge-Base_dSbXPwSgGqG --output my_output.md --spider_api_key YOUR_API_KEY
```

## Configuration

You can adjust the scraper's behavior by modifying these variables in `enhanced_scraper.py`:

- `CRAWLER_PARAMS`: Settings for the Spider API calls
- `SYSTEM_PROMPT`: Instructions for the LLM to clean content
- Semaphore limit in `crawl_coda_documentation`: Controls concurrency

## Output

The scraper generates a Markdown file containing:

1. A header with the URL being scraped
2. The cleaned content for each page
3. Separator lines between different pages

## Troubleshooting

- If you encounter rate limits with the Spider API, try lowering the concurrency by adjusting the semaphore value.
- For OpenAI API errors, check your API key and ensure you have sufficient credits.
- For memory issues with large documents, try reducing the `limit` in `CRAWLER_PARAMS`.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 