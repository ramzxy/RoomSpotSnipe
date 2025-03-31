import os
import time
import json
import requests
from dotenv import load_dotenv
import discord
from discord import Webhook
import aiohttp
import asyncio
import re
import traceback
import urllib.parse
# Load environment variables
load_dotenv()

# Constants
API_URL = "https://studentenenschede-aanbodapi.zig365.nl/api/v1/actueel-aanbod?limit=60&locale=en_GB&page=0&sort=%2BreactionData.aangepasteTotaleHuurprijs"
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
CHECK_INTERVAL = 300  # 5 minutes

# Filters payload for Enschede (municipality.id: 15897)
API_PAYLOAD = {
    "hidden-filters": {
        "$and": [
            {"dwellingType.categorie": {"$eq": "woning"}},
            {"rentBuy": {"$eq": "Huur"}},
            {"isExtraAanbod": {"$eq": ""}},
            {"isWoningruil": {"$eq": ""}},
            {
                "$and": [
                    {
                        "$or": [
                            {"street": {"$like": ""}},
                            {"houseNumber": {"$like": ""}},
                            {"houseNumberAddition": {"$like": ""}}
                        ]
                    },
                    {
                        "$or": [
                            {"street": {"$like": ""}},
                            {"houseNumber": {"$like": ""}},
                            {"houseNumberAddition": {"$like": ""}}
                        ]
                    }
                ]
            }
        ]
    }
}

# Headers to mimic a browser request
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
    'Content-Type': 'application/json'
}

async def get_listings():
    """Fetch listings from the API with the Enschede filters."""
    listings = []
    
    try:
        print("Fetching listings from API...")
        async with aiohttp.ClientSession() as session:
            # Make a POST request with the filters payload
            async with session.post(
                API_URL, 
                headers=HEADERS,
                json=API_PAYLOAD
            ) as response:
                if response.status != 200:
                    print(f"Error: API returned status code {response.status}")
                    return listings
                
                data = await response.json()
                
                print(f"API response keys: {data.keys() if data else 'None'}")
                
                # Check if the response has the structure with 'data' key
                if data and 'data' in data:
                    items = data['data']
                    print(f"API returned {len(items)} items")
                    
                    # Process each listing
                    for item in items:
                        try:
                            # Extract listing details
                            listing_id = str(item.get('id', ''))
                            
                            # Extract address components directly from API response
                            street = item.get('street', '')
                            house_number = item.get('houseNumber', '')
                            house_number_addition = item.get('houseNumberAddition', '')
                            
                            # Get city info
                            city_name = item.get('gemeenteGeoLocatieNaam', '')
                            
                            postal_code = item.get('postalcode', '')
                            
                            # Format the title
                            title_parts = [p for p in [street, house_number, house_number_addition] if p]
                            title = f"{' '.join(title_parts)}"
                            if postal_code or city_name:
                                title += f", {postal_code} {city_name}".strip()
                            
                            # Extract price
                            price = ''
                            if item.get('totalRent'):
                                price = f"€{float(item['totalRent']):.2f}"
                            elif item.get('netRent'):
                                price = f"€{float(item['netRent']):.2f}"
                            else:
                                price = 'No price info'
                            
                            # Extract area
                            area = ''
                            if item.get('areaDwelling'):
                                area = f"{item['areaDwelling']} m²"
                            else:
                                area = 'No area info'
                            
                            # Extract property type
                            property_type = ''
                            if isinstance(item.get('dwellingType'), dict):
                                property_type = item['dwellingType'].get('localizedName', '')
                            else:
                                property_type = item.get('objectType', '')
                            
                            house_type = ''
                            if isinstance(item.get('woningsoort'), dict):
                                house_type = item['woningsoort'].get('localizedNaam', '')
                            else:
                                house_type = item['toewijzingModelCategorie'].get('code', '')

                            # Extract image URL
                            img_url = ''
                            if item.get('pictures') and len(item['pictures']) > 0:
                                if isinstance(item['pictures'][0], dict) and 'url' in item['pictures'][0]:
                                    img_url = item['pictures'][0]['url']
                                elif isinstance(item['pictures'][0], dict) and 'uri' in item['pictures'][0]:
                                    img_url = item['pictures'][0]['uri']
                            
                            # Ensure img_url is a complete URL
                            if img_url and not img_url.startswith(('http://', 'https://')):
                                img_url = f"https://www.roomspot.nl{img_url}"
                            
                            # Extract publication date∑ß
                            publication_date = item.get('publicationDate', '')
                            
                            # Create clean components for URL
                            components = [str(listing_id)]
                            
                            if street:
                                # Remove spaces from street names
                                clean_street = street.lower().strip().replace(" ", "")
                                components.append(clean_street)
                            
                            if house_number:
                                components.append(str(house_number))
                            
                            if house_number_addition:
                                # Remove spaces and format the addition
                                addition = str(house_number_addition).strip().replace(" ", "")
                                if addition:
                                    components.append(addition)
                            
                            if city_name:
                                # Also remove spaces from city name for consistency
                                clean_city = city_name.lower().strip().replace(" ", "")
                                components.append(clean_city)
                            
                            # Join with hyphens to create a clean URL
                            clean_url_path = "-".join(components)
                            
                            # Create the final link
                            link = f"https://www.roomspot.nl/en/housing-offer/to-rent/translate-to-engels-details/{clean_url_path}"
                            
                            # Only include listings with a valid title
                            if not title or title.isspace():
                                print(f"Skipping listing {listing_id} with empty title")
                                continue
                            
                            listing = {
                                'id': listing_id,
                                'title': title,
                                'price': price,
                                'area': area,
                                'property_type': property_type,
                                'house_type': house_type,
                                'link': link,
                                'img_url': img_url,
                                'publication_date': publication_date,
                                'timestamp': time.time()
                            }
                            
                            listings.append(listing)
                            
                        except Exception as e:
                            print(f"Error processing listing: {e}")
                            continue
                    
                    print(f"Found {len(listings)} Enschede listings")
                else:
                    print("Error: API response doesn't have expected 'data' key")
        
    except Exception as e:
        print(f"Error fetching listings from API: {e}")
    
    return listings

async def send_discord_notification(listing):
    """Send a notification to Discord about a new listing."""
    try:
        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(DISCORD_WEBHOOK_URL, session=session)
            
            embed = discord.Embed(
                title="New Apartment Listing! 🏠",
                description=f"**{listing['title']}**",
                color=discord.Color.green(),
                url=listing['link']
            )
            
            # Add fields with details
            embed.add_field(name="Price", value=listing['price'], inline=True)
            embed.add_field(name="Area", value=listing['area'], inline=True)
            embed.add_field(name="Property Type", value=listing['property_type'], inline=True)
            
            if listing.get('house_type'):
                embed.add_field(name="House Type", value=listing['house_type'], inline=True)
            
            print(listing['img_url'])
            print(listing['link'])
            # Add image if available
            if listing['img_url']:
                embed.set_image(url=listing['img_url'])
            
            # Add footer with timestamp
            embed.set_footer(text=f"Found on {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(listing['timestamp']))}")
            
            await webhook.send(embed=embed)
            print(f"Sent notification for: {listing['title']}")
    except Exception as e:
        print(f"Error sending Discord notification: {e}")

def load_seen_listings():
    """Load previously seen listings from a JSON file."""
    try:
        with open('seen_listings.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_seen_listings(listings):
    """Save seen listings to a JSON file."""
    with open('seen_listings.json', 'w') as f:
        json.dump(listings, f)

async def main():
    """Main function to run the scraper."""
    print("🎯 Starting Roomspot sniper...")
    seen_listings = load_seen_listings()
    print(f"Loaded {len(seen_listings)} previously seen listings")
    
    # First run - use debug mode
    
    while True:
        try:
            print("Fetching current listings...")
            current_listings = await get_listings()
            print(f"Found {len(current_listings)} listings in total")
            
            if not current_listings:
                print("No listings were found. Retrying in 60 seconds...")
                await asyncio.sleep(60)
                continue
            
            # Check for new listings
            new_listings = []
            for listing in current_listings:
                if listing['id'] not in seen_listings:
                    print(f"New listing found: {listing['title']} (ID: {listing['id']})")
                    new_listings.append(listing)
                    seen_listings.append(listing['id'])
                else:
                    print(f"Known listing: {listing['title']} (ID: {listing['id']})")
            
            print(f"Found {len(new_listings)} new listings")
            
            # Send notifications for new listings
            for listing in new_listings:
                print(f"Sending notification for: {listing['title']}")
                await send_discord_notification(listing)
            
            # Save updated seen listings
            save_seen_listings(seen_listings)
            
            
            await asyncio.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"Error in main loop: {e}")
            print("Traceback:", traceback.format_exc())
            await asyncio.sleep(60)  # Wait a minute before retrying

if __name__ == "__main__":
    asyncio.run(main()) 
