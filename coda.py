import os
import asyncio
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import json

# Load environment variables
load_dotenv()

class CodaConfig(BaseModel):
    """Configuration for Coda API client."""
    api_token: str = Field(..., description="Coda API token")
    base_url: str = Field(default="https://coda.io/apis/v1", description="Coda API base URL")
    doc_id: Optional[str] = None

class CodaClient:
    """Async client for interacting with Coda API."""
    
    def __init__(self, config: CodaConfig):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.api_token}",
            "Content-Type": "application/json"
        }
        # Print first 8 chars of token for debugging
        print(f"Using API token: {config.api_token[:8]}...")
    
    async def _make_request(self, method: str, url: str) -> Dict:
        """Make a request to the Coda API with detailed error handling."""
        print(f"\nMaking {method} request to: {url}")
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.request(method, url) as response:
                print(f"Response status: {response.status}")
                print(f"Response headers: {response.headers}")
                
                try:
                    response_json = await response.json()
                    print(f"Response body: {json.dumps(response_json, indent=2)}")
                    
                    if response.status != 200:
                        raise Exception(f"API request failed with status {response.status}: {response_json.get('message', 'Unknown error')}")
                    
                    return response_json
                except json.JSONDecodeError as e:
                    raise Exception(f"Failed to decode JSON response: {e}")
    
    async def list_docs(self) -> List[Dict]:
        """List all accessible documents."""
        url = f"{self.config.base_url}/docs"
        response = await self._make_request("GET", url)
        return response.get("items", [])
    
    async def get_doc_info(self) -> Dict:
        """Get information about the document."""
        if not self.config.doc_id:
            raise ValueError("Document ID is required for this operation")
        url = f"{self.config.base_url}/docs/{self.config.doc_id}"
        return await self._make_request("GET", url)
    
    async def get_pages(self) -> List[Dict]:
        """Get all pages in the document."""
        if not self.config.doc_id:
            raise ValueError("Document ID is required for this operation")
        url = f"{self.config.base_url}/docs/{self.config.doc_id}/pages"
        response = await self._make_request("GET", url)
        return response.get("items", [])
    
    async def get_page_content(self, page_id: str) -> Dict:
        """Get content of a specific page."""
        if not self.config.doc_id:
            raise ValueError("Document ID is required for this operation")
        url = f"{self.config.base_url}/docs/{self.config.doc_id}/pages/{page_id}/content"
        return await self._make_request("GET", url)
    
    async def get_tables(self) -> List[Dict]:
        """Get all tables in the document."""
        if not self.config.doc_id:
            raise ValueError("Document ID is required for this operation")
        url = f"{self.config.base_url}/docs/{self.config.doc_id}/tables"
        response = await self._make_request("GET", url)
        return response.get("items", [])
    
    async def get_table_rows(self, table_id: str) -> List[Dict]:
        """Get all rows from a specific table."""
        if not self.config.doc_id:
            raise ValueError("Document ID is required for this operation")
        url = f"{self.config.base_url}/docs/{self.config.doc_id}/tables/{table_id}/rows"
        response = await self._make_request("GET", url)
        return response.get("items", [])

async def list_accessible_docs() -> List[Dict]:
    """List all documents accessible with the current API token."""
    api_token = os.getenv("CODA_API_TOKEN")
    if not api_token:
        raise ValueError("CODA_API_TOKEN not found in environment variables")
    
    print(f"Using API token: {api_token[:8]}...")
    
    config = CodaConfig(api_token=api_token)
    client = CodaClient(config)
    
    print("\nListing accessible documents:")
    docs = await client.list_docs()
    for doc in docs:
        print(f"\nDocument ID: {doc.get('id')}")
        print(f"Name: {doc.get('name')}")
        print(f"Type: {doc.get('type')}")
        print(f"Owner: {doc.get('owner', {}).get('name', 'N/A')}")
        print(f"Created: {doc.get('createdAt')}")
        print(f"Last Modified: {doc.get('updatedAt')}")
    return docs

async def extract_doc_content(doc_id: str) -> Dict:
    """Extract all content from a Coda document."""
    api_token = os.getenv("CODA_API_TOKEN")
    if not api_token:
        raise ValueError("CODA_API_TOKEN not found in environment variables")
    
    print(f"Using API token: {api_token[:8]}...")
    
    config = CodaConfig(
        api_token=api_token,
        doc_id=doc_id
    )
    
    client = CodaClient(config)
    
    content = {
        "doc_info": await client.get_doc_info(),
        "pages": [],
        "tables": []
    }
    
    # Get pages and their content
    pages = await client.get_pages()
    for page in pages:
        page_content = await client.get_page_content(page["id"])
        content["pages"].append({
            "page_info": page,
            "content": page_content
        })
    
    # Get tables and their rows
    tables = await client.get_tables()
    for table in tables:
        table_rows = await client.get_table_rows(table["id"])
        content["tables"].append({
            "table_info": table,
            "rows": table_rows
        })
    
    return content

async def main():
    """Main function to extract content from the specified Coda document."""
    # First, list all accessible documents
    print("Checking accessible documents...")
    await list_accessible_docs()
    
    # Then try to access the specific document
    doc_id = "SbXPwSgG"  # Correct document ID without the 'd' prefix
    print(f"\nAttempting to access document with ID: {doc_id}")
    
    try:
        content = await extract_doc_content(doc_id)
        
        # Save the extracted content to a file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"coda_content_{timestamp}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, ensure_ascii=False)
        
        print(f"Content successfully extracted and saved to {output_file}")
        
    except Exception as e:
        print(f"Failed to extract content: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
