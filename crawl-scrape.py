import asyncio
import logging
import os
import sys
import time
from urllib.parse import urlparse

import aiofiles
import openai
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler


# Load environment variables (for OpenAI API key)
load_dotenv()

# Set up your OpenAI API key
openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# System prompt to clean up the text
SYSTEM_PROMPT = """
You are a helpful assistant designed to clean up text data from web pages. 
Your task is to remove redundant and unnecessary parts while keeping the relevant information intact. 
Ensure that the cleaned text is concise, organized, and easy to read, but do not alter the actual content.

Instructions:
- Remove any navigation bars, menus, headers, footers, and repeated sections.
- Remove any 'skip to content' or similar irrelevant phrases.
- Ensure that the final text is coherent and structured logically.

Strictly return the cleaned text in markdown format, making sure that the end of the text is separated by a new line or '---' without modifying the actual content or its meaning.
"""

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


# Rate limiting for LLM API calls
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
rate_limiter = RateLimiter(25, 60)  # 25 calls per minute


async def clean_text_with_llm(raw_text, semaphore):
    """Send the raw text to the LLM for cleaning with retry logic."""
    max_retries = 5
    initial_delay = 3
    retries = 0
    
    while retries < max_retries:
        try:
            async with semaphore, rate_limiter:
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
                    return response.choices[0].message.content
        except Exception as e:
            retries += 1
            logging.warning(f"LLM cleaning attempt {retries} failed: {e}")
            delay = initial_delay * (2 ** retries)
            logging.info(f"Waiting for {delay} seconds before retrying LLM cleaning...")
            await asyncio.sleep(delay)
    
    logging.error("Max retries reached for LLM cleaning. Returning original text.")
    return raw_text


async def process_results(result, output_file, semaphore):
    """Process the crawling results, clean with LLM, and save to file."""
    if not result.markdown:
        logging.warning(f"No content extracted from {result.url}. Skipping.")
        return
    
    logging.info(f"Cleaning content from {result.url}")
    cleaned_text = await clean_text_with_llm(result.markdown, semaphore)
    
    async with aiofiles.open(output_file, "a", encoding="utf-8") as file:
        await file.write(f"URL: {result.url}\n\n")
        await file.write(cleaned_text + "\n\n")
        await file.write("=" * 80 + "\n\n")  # Separator


# Custom JavaScript to extract links and content from Coda docs
CODA_EXTRACT_LINKS_JS = """
function extractCodaLinks() {
    // Get all links from the sidebar navigation
    const sidebarLinks = Array.from(document.querySelectorAll('.doc-table-of-contents-item a')).map(a => a.href);
    
    // Get all section links within the document
    const sectionLinks = Array.from(document.querySelectorAll('.table-of-contents-entry a')).map(a => a.href);
    
    // Get all button links that might open additional sections
    const buttonLinks = Array.from(document.querySelectorAll('button[data-href]')).map(btn => btn.getAttribute('data-href'));
    
    // Get any other relevant links (customize based on Coda's structure)
    const otherLinks = Array.from(document.querySelectorAll('.doc-section-link, .page-link, .anchor-link')).map(a => a.href);
    
    // Combine all links and remove duplicates
    const allLinks = [...new Set([...sidebarLinks, ...sectionLinks, ...buttonLinks, ...otherLinks])];
    
    // Filter out non-document links or external links
    return allLinks.filter(link => link && link.includes('coda.io/d/') && !link.includes('mailto:'));
}

// Extract and return all links
return extractCodaLinks();
"""

# JavaScript to extract dynamic content and expand all sections
CODA_EXPAND_CONTENT_JS = """
async function expandCodaContent() {
    // Wait for the main content to load
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Click all "Show more" buttons
    const expandButtons = Array.from(document.querySelectorAll('button'))
        .filter(btn => btn.textContent.includes('Show more') || 
                      btn.textContent.includes('Expand') ||
                      btn.textContent.includes('+'));
    
    for (const button of expandButtons) {
        try {
            button.click();
            // Wait a bit between clicks
            await new Promise(resolve => setTimeout(resolve, 500));
        } catch (e) {
            console.error('Error clicking button:', e);
        }
    }
    
    // Expand all collapsible sections
    const collapsibleSections = Array.from(document.querySelectorAll('.collapsible, .expandable, [aria-expanded="false"]'));
    for (const section of collapsibleSections) {
        try {
            section.click();
            await new Promise(resolve => setTimeout(resolve, 500));
        } catch (e) {
            console.error('Error expanding section:', e);
        }
    }
    
    // Return true to indicate completion
    return true;
}

// Execute and return result
return await expandCodaContent();
"""


async def main():
    # Define the URL to scrape
    base_url = "https://coda.io/d/PlanYear-Client-Knowledge-Base_dSbXPwSgGqG"
    output_file = "coda_knowledge_base.txt"
    
    # Set up logging
    set_up_logging(base_url)
    
    # Create a semaphore to limit concurrent LLM requests
    semaphore = asyncio.Semaphore(20)  # Limit to 20 concurrent requests
    
    # Track processed URLs
    processed_urls = set()
    
    try:
        # Initialize the crawler with configuration for browser automation
        async with AsyncWebCrawler(
            # Configure crawler options specifically for Coda
            crawler_config={
                "max_depth": 10,  # Increased depth to catch nested pages
                "max_pages": 100,  # Increased from default
                "follow_subdomains": True,
                "max_concurrent": 4,  # Reduced to be gentler on the server
                "timeout": 120,  # Increased timeout for SPA
                "retry_attempts": 5,
                "use_browser": True,  # Enable browser automation for JS rendering
                "browser_options": {
                    "headless": True,
                    "wait_for": 5000,  # Wait 5 seconds for page to load
                }
            }
        ) as crawler:
            # Start with the base URL
            urls_to_process = [base_url]
            
            while urls_to_process:
                current_url = urls_to_process.pop(0)
                
                if current_url in processed_urls:
                    continue
                
                processed_urls.add(current_url)
                logging.info(f"Processing {current_url}")
                
                # Crawl the current URL with browser automation
                result = await crawler.arun(
                    url=current_url,
                    options={
                        "extract_content": True,
                        "extract_links": True,
                        "extract_metadata": True,
                        "wait_for": 5000,  # Wait 5 seconds for page load
                        "headers": {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                        },
                        "js_before_extract": CODA_EXPAND_CONTENT_JS,  # Expand content before extraction
                    }
                )
                
                # Process and save the result
                await process_results(result, output_file, semaphore)
                
                # Extract more links using custom JavaScript
                additional_links = await crawler.run_js(
                    url=current_url,
                    js_code=CODA_EXTRACT_LINKS_JS
                )
                
                if additional_links and isinstance(additional_links, list):
                    logging.info(f"Found {len(additional_links)} additional links from {current_url}")
                    # Add new links to process
                    for link in additional_links:
                        if link and link not in processed_urls and "coda.io/d/" in link:
                            urls_to_process.append(link)
                
                # Be nice to the server
                await asyncio.sleep(2)
            
            logging.info(f"Crawling completed. Processed {len(processed_urls)} pages. Results saved to {output_file}")
    
    except Exception as e:
        logging.error(f"Error during crawling: {e}")


if __name__ == "__main__":
    print("Starting Crawl4AI scraper for Coda.io knowledge base...")
    print("This will use browser automation to handle dynamic content.")
    print("Press Ctrl+C to stop the scraping process.")
    
    # Ensure Playwright browsers are installed
    import subprocess
    try:
        print("Checking if Playwright browsers are installed...")
        subprocess.run(["playwright", "install", "chromium"], check=True)
        print("Playwright browsers installed successfully.")
    except Exception as e:
        print(f"Error installing Playwright browsers: {e}")
        print("Please run 'playwright install' manually before running this script.")
    
    try:
        asyncio.run(main())
        print(f"Scraping complete. Check the logs for details.")
    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
    except Exception as e:
        print(f"Critical error: {e}")
        print("Check the log file for details.")
