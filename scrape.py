import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
import time
import logging
import openai
import os
import argparse
import re
import sys
import asyncio
import aiofiles
import urllib.parse
from asyncio import Semaphore

"""
This script is designed to scrape documentation websites and extract the text content of each page.
It uses a combination of LLM cleaning and a retry mechanism to handle errors and fetch the content from the URLs.

Usage:
    python scrape_2.py https://example.com/docs --output example_docs.txt

    This command will scrape the documentation at https://example.com/docs and save the output to example_docs.txt.

Arguments:
    base_url: The base URL of the documentation website to scrape.
    --output: (Optional) The name of the output file. Defaults to "docs_output.txt" if not specified.

The script supports a wide range of documentation website URL patterns and can be customized for different sites.
"""

## This script is designed to scrape documentation websites and extract the text content of each page. 
## It uses a combination of LLM cleaning and a retry mechanism to handle errors and fetch the content from the URLs.
## Upgrade: add a method to customize the url
## Upgrade: Add support for more forms of documentation websites. eg github wiki, gitbook, etc.

# Load environment variables (for OpenAI API key)
load_dotenv()

# Set up your OpenAI API key
openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Replace the existing visited_urls set with a more comprehensive structure
visited_urls = {}

# Set up logging
def get_log_file_name(base_url):
    """Generate a custom log file name based on the domain of the base URL."""
    domain = urlparse(base_url).netloc
    return f"{domain.replace('.', '_')}_scraping.log"

def set_up_logging(base_url):
    """Set up logging with a custom log file name based on the domain of the base URL."""
    log_file = get_log_file_name(base_url)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="w"),
            logging.StreamHandler(sys.stdout)
        ]
    )

# System prompt to clean up the text
SYSTEM_PROMPT = """
You are a helpful assistant designed to clean up text data from web pages. 
Your task is to remove redundant and unnecessary parts while keeping the relevant information intact. 
Ensure that the cleaned text is concise, organized, and easy to read, but do not alter the actual content.

Instructions:
- Remove any navigation bars, menus, headers, footers, and repeated sections.
- Remove any 'skip to content' or similar irrelevant phrases.
- Ensure that the final text is coherent and structured logically.

Strictly return the cleaned text in markdown format, making sure that the end of the text is seperated by a new line or '---' without modifying the actual content or its meaning.
"""

# Constants for retry logic
INITIAL_DELAY = 3  # seconds
MAX_RETRIES = 5  # Maximum retry attempts
MAX_DELAY = 60  # Maximum delay between retries in seconds
LLM_FAILURE_LIMIT = 18  # Stop after 18 consecutive LLM failures
LLM_FAILURE_COUNT = 0  # Initialize LLM failure counter

# Headers to mimic a real browser request
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

# Replace requests.Session() with httpx.AsyncClient()
async def get_client():
    return httpx.AsyncClient(headers=HEADERS, follow_redirects=True)

async def is_valid_url(url, base_url):
    """Check if the URL is within the same domain and should be scraped."""
    parsed_base = urlparse(base_url)
    parsed_url = urlparse(url)
    
    # Check if the domains match
    if parsed_base.netloc != parsed_url.netloc:
        return False
    
    # Check if the URL is not a file (e.g., PDF, image)
    if parsed_url.path.lower().endswith(('.pdf', '.jpg', '.png', '.gif')):
        return False
    
    # Allow URLs with query parameters
    return True

async def normalize_url(url):
    """Normalize the URL by removing fragments and sorting query parameters."""
    parsed = urlparse(url)
    # Remove fragment
    cleaned = parsed._replace(fragment='')
    
    # Sort query parameters
    query_params = parse_qs(cleaned.query)
    sorted_query = urlencode(sorted(query_params.items()), doseq=True)
    cleaned = cleaned._replace(query=sorted_query)
    
    return urlunparse(cleaned)

async def fetch_url_content(url, client):
    """Fetch the content from the URL with retry logic, skip on 403 or 404 errors."""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            response = await client.get(url)
            if response.status_code in [404, 403]:
                logging.warning(f"{response.status_code} Error: Skipping {url}")
                return None
            response.raise_for_status()
            return response.content
        except httpx.RequestError as e:
            retries += 1
            logging.warning(f"Attempt {retries} failed for {url}: {e}")
            delay = min(INITIAL_DELAY * (2 ** retries), MAX_DELAY)
            logging.info(f"Waiting for {delay} seconds before retrying {url}...")
            await asyncio.sleep(delay)
    logging.error(f"Max retries reached for {url}. Skipping.")
    return None

# Add these constants at the top of the file
MAX_CONCURRENT_REQUESTS = 20  # Adjusted for Token Limit of 20000 per minute
REQUESTS_PER_MINUTE = 25

# Create a semaphore to limit concurrent requests
api_semaphore = Semaphore(MAX_CONCURRENT_REQUESTS)

# Create a rate limiter
class RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = asyncio.Lock()

    async def __aenter__(self):
        async with self.lock:
            now = time.time()
            self.calls = [call for call in self.calls if call > now - self.period]
            if len(self.calls) >= self.max_calls:
                sleep_time = self.calls[0] - (now - self.period)
                await asyncio.sleep(sleep_time)
            self.calls.append(time.time())

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

# Create a rate limiter instance
rate_limiter = RateLimiter(REQUESTS_PER_MINUTE, 60)

async def clean_text_with_llm(raw_text):
    """Send the raw text to the LLM for cleaning with retry logic, stop after 18 consecutive failures."""
    global LLM_FAILURE_COUNT
    retries = 0
    while retries < MAX_RETRIES:
        try:
            async with api_semaphore, rate_limiter:
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": raw_text},
                ]
                response = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0,  # little to no randomness
                    messages=messages,
                )
                if response.choices:
                    LLM_FAILURE_COUNT = 0  # Reset LLM failure count on success
                    return response.choices[0].message.content
        except Exception as e:
            retries += 1
            LLM_FAILURE_COUNT += 1
            logging.warning(f"LLM cleaning attempt {retries} failed: {e}")
            if retries % 3 == 0:
                logging.info("Waiting for 10 seconds before retrying LLM cleaning...")
                await asyncio.sleep(10)
            else:
                await asyncio.sleep(INITIAL_DELAY)

            if LLM_FAILURE_COUNT >= LLM_FAILURE_LIMIT:
                logging.critical("18 consecutive LLM failures. Stopping the script.")
                raise Exception(
                    "Too many consecutive LLM failures. Stopping the script."
                )
    logging.error("Max retries reached for LLM cleaning. Skipping.")
    return ""

async def extract_text_from_url(url, client):
    """Fetch and parse the webpage content, then clean it using LLM."""
    content = await fetch_url_content(url, client)
    if content is None:
        return "", []

    soup = BeautifulSoup(content, "html.parser")

    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()

    # Extract raw text content
    raw_text_content = soup.get_text()
    cleaned_text = "\n".join(
        [line.strip() for line in raw_text_content.splitlines() if line.strip()]
    )

    # Clean the text using the LLM
    cleaned_text = await clean_text_with_llm(cleaned_text)

    # Extract and return all valid links within the page
    links = soup.find_all("a", href=True)
    page_links = []
    for link in links:
        full_url = urljoin(url, link["href"])
        normalized_url = await normalize_url(full_url)
        if await is_valid_url(normalized_url, base_url):
            page_links.append(normalized_url)
    
    # Look for pagination links
    pagination_links = await find_pagination_links(soup, url)
    page_links.extend(pagination_links)

    return cleaned_text, list(set(page_links))  # Remove duplicates

async def find_pagination_links(soup, current_url):
    """Find pagination links in the page."""
    pagination_links = set()
    base_url = urlparse(current_url).scheme + "://" + urlparse(current_url).netloc
    
    # Look for common pagination patterns
    pagination_elements = soup.find_all(class_=re.compile(r'pagination|pager|nav'))
    for element in pagination_elements:
        links = element.find_all('a', href=True)
        for link in links:
            full_url = urljoin(current_url, link["href"])
            normalized_url = await normalize_url(full_url)
            if await is_valid_url(normalized_url, base_url):
                pagination_links.add(normalized_url)
    
    # Look for "Next" or "Previous" links
    next_links = soup.find_all('a', string=re.compile(r'next|forward', re.I), href=True)
    prev_links = soup.find_all('a', string=re.compile(r'previous|back', re.I), href=True)
    for link in next_links + prev_links:
        full_url = urljoin(current_url, link["href"])
        normalized_url = await normalize_url(full_url)
        if await is_valid_url(normalized_url, base_url):
            pagination_links.add(normalized_url)
    
    # Look for sidebar navigation links
    sidebar_elements = soup.find_all(class_=re.compile(r'sidebar|menu|toc'))
    for element in sidebar_elements:
        links = element.find_all('a', href=True)
        for link in links:
            full_url = urljoin(current_url, link["href"])
            normalized_url = await normalize_url(full_url)
            if await is_valid_url(normalized_url, base_url):
                pagination_links.add(normalized_url)
    
    # Look for query parameter-based navigation
    links_with_params = soup.find_all('a', href=re.compile(r'\?'))
    for link in links_with_params:
        full_url = urljoin(current_url, link["href"])
        normalized_url = await normalize_url(full_url)
        if await is_valid_url(normalized_url, base_url):
            pagination_links.add(normalized_url)
    
    return list(pagination_links)

async def is_subdirectory(url, base_url):
    """Check if the given URL is a subdirectory of the base URL."""
    parsed_url = urllib.parse.urlparse(url)
    parsed_base = urllib.parse.urlparse(base_url)
    
    return (parsed_url.scheme == parsed_base.scheme and
            parsed_url.netloc == parsed_base.netloc and
            parsed_url.path.startswith(parsed_base.path))

async def traverse_and_extract(url, output_file, client, base_url):
    """Recursively traverse through each URL and extract content."""
    normalized_url = await normalize_url(url)
    
    # Check if the URL has been visited or is not a subdirectory of the base URL
    if normalized_url in visited_urls or not await is_subdirectory(normalized_url, base_url):
        return

    visited_urls[normalized_url] = True
    logging.info(f"Scraping {normalized_url}")

    try:
        cleaned_text, links = await extract_text_from_url(normalized_url, client)
        if cleaned_text == "":
            logging.warning(f"No content extracted from {normalized_url}. Skipping.")
            return
    except Exception as e:
        logging.error(f"Error during scraping {normalized_url}: {e}")
        return

    # Write the cleaned text to the file
    async with aiofiles.open(output_file, "a", encoding="utf-8") as file:
        await file.write(f"URL: {normalized_url}\n\n")
        await file.write(cleaned_text + "\n\n")
        await file.write("=" * 80 + "\n\n")  # Separator

    # Pause briefly between requests to avoid overloading the server
    await asyncio.sleep(2)  # Increased delay to be more considerate

    # Recursively traverse through each link
    tasks = []
    for link in links:
        if link not in visited_urls and await is_subdirectory(link, base_url):
            tasks.append(traverse_and_extract(link, output_file, client, base_url))
    await asyncio.gather(*tasks)

async def main(base_url, output_file):
    async with await get_client() as client:
        await traverse_and_extract(base_url, output_file, client, base_url)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape documentation websites")
    parser.add_argument("base_url", help="Base URL of the documentation website")
    parser.add_argument("--output", default="docs_output.txt", help="Output file name")
    args = parser.parse_args()

    base_url = args.base_url
    start_url = base_url
    output_file = args.output

    # Generate custom log file name
    log_file = get_log_file_name(base_url)

    # Set up logging with the custom log file name
    set_up_logging(base_url)

    print(f"Scraping started. Log file: {log_file}")
    print("Press Ctrl+C to stop the scraping process.")

    try:
        asyncio.run(main(start_url, output_file))
        logging.info(
            f"Text extraction and cleaning complete. Check the {output_file} file."
        )
    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
    except Exception as e:
        logging.critical(f"Critical error: {e}")
        print("An error occurred. Check the log file for details.")

    print(f"Scraping finished. Log file saved as: {log_file}")

# Example usage:
# uv run python3 scrape_2_async.py https://docs.pydantic.dev/latest/ --output pydantic_v2_docs.txt
# uv run python3 scrape_2_async.py https://python-client.qdrant.tech/ --output qdrant_python_client_docs.txt
# uv run python3 scrape_2_async.py https://docs.astral.sh/uv/ --output uv_docs_latest.txt
# uv run python3 scrape_2_async.py https://ai.pydantic.dev/ --output pydantic_ai_docs.txt
# uv run python3 scrape.py https://langchain-ai.github.io/langgraph/ --output langgraph_docs.txt
# uv run python3 scrape.py https://docs.crewai.com/ --output crewai_docs_latest.txt
# uv run python3 scrape.py https://coda.io/d/PlanYear-Client-Knowledge-Base_dSbXPwSgGqG --output coda_docs.txt
# uv run python3 scrape.py https://qdrant.github.io/fastembed/ --output fastembed_docs.txt