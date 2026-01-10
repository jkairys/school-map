#!/usr/bin/env python3
"""CLI entry point for the Brisbane Property Scraper."""

import argparse
import asyncio
import sys
from pathlib import Path

from src.config import OUTPUT_DIR, COMBINED_DIR, load_suburbs
from src.scraper import BrisbanePropertyScraper
from src.storage import SuburbStorage, combine_suburb_files


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape Brisbane property sold data from onthehouse.com.au",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape a single suburb
  %(prog)s --suburb paddington

  # Scrape with more pages
  %(prog)s --suburb new-farm --max-pages 10

  # Scrape all suburbs
  %(prog)s --all

  # List available suburbs
  %(prog)s --list-suburbs

  # Combine all suburb files
  %(prog)s --combine
        """
    )

    # Mode selection (mutually exclusive)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--suburb", "-s",
        help="Scrape a single suburb (e.g., 'paddington' or 'st-lucia')"
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="Scrape all suburbs in the suburbs.json file"
    )
    mode.add_argument(
        "--list-suburbs",
        action="store_true",
        help="List all available suburbs and their postcodes"
    )
    mode.add_argument(
        "--combine",
        action="store_true",
        help="Combine all suburb files into one master file"
    )

    # Scraping options
    parser.add_argument(
        "--max-pages", "-p",
        type=int,
        default=5,
        help="Maximum pages to scrape per suburb (default: 5)"
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Skip fetching individual property details (faster but less data)"
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Run browser in visible mode (not headless)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Output directory (default: {OUTPUT_DIR})"
    )

    return parser.parse_args()


async def scrape_single_suburb(args):
    """Scrape a single suburb.
    
    Args:
        args: Parsed command line arguments
    """
    scraper = BrisbanePropertyScraper(headless=not args.visible)
    
    # Normalize suburb name
    suburb_key = args.suburb.lower().replace(" ", "-")
    
    # Check if suburb exists
    if suburb_key not in scraper.suburbs:
        print(f"Error: Unknown suburb '{args.suburb}'")
        print(f"Use --list-suburbs to see all available suburbs")
        return
    
    postcode = scraper.suburbs[suburb_key]
    storage = SuburbStorage(suburb_key, args.output_dir)

    print(f"\n{'='*60}")
    print(f"Scraping {suburb_key.replace('-', ' ').title()}, QLD {postcode}")
    print(f"{'='*60}")
    print(f"Max pages: {args.max_pages}")
    print(f"Fetch details: {not args.no_details}")
    print(f"Output: {storage.filename}")
    print(f"{'='*60}\n")

    properties = await scraper.scrape_suburb(
        suburb=suburb_key,
        storage=storage,
        max_pages=args.max_pages,
        fetch_details=not args.no_details,
        save_incrementally=True
    )

    print(f"\n{'='*60}")
    print(f"Completed: {len(properties)} properties saved to {storage.filename}")
    print(f"{'='*60}\n")


async def scrape_all_suburbs(args):
    """Scrape all suburbs sequentially.
    
    Args:
        args: Parsed command line arguments
    """
    suburbs = load_suburbs()
    scraper = BrisbanePropertyScraper(headless=not args.visible)

    print(f"\n{'='*60}")
    print(f"Brisbane Property Scraper - All Suburbs Mode")
    print(f"{'='*60}")
    print(f"Total suburbs: {len(suburbs)}")
    print(f"Max pages per suburb: {args.max_pages}")
    print(f"Fetch details: {not args.no_details}")
    print(f"Output directory: {args.output_dir}")
    print(f"{'='*60}\n")

    total_properties = 0

    for i, (suburb, postcode) in enumerate(suburbs.items(), 1):
        print(f"\n[{i}/{len(suburbs)}] {suburb.replace('-', ' ').title()}, QLD {postcode}")
        print("-" * 60)
        
        storage = SuburbStorage(suburb, args.output_dir)

        try:
            properties = await scraper.scrape_suburb(
                suburb=suburb,
                storage=storage,
                max_pages=args.max_pages,
                fetch_details=not args.no_details,
                save_incrementally=True
            )
            
            print(f"  Completed: {len(properties)} properties")
            total_properties += len(properties)
            
        except Exception as e:
            print(f"  Error: {e}")
            continue

    print(f"\n{'='*60}")
    print(f"ALL SUBURBS COMPLETED")
    print(f"{'='*60}")
    print(f"Total properties scraped: {total_properties}")
    print(f"Output directory: {args.output_dir}")
    print(f"{'='*60}\n")


def list_suburbs():
    """List all available suburbs."""
    suburbs = load_suburbs()
    
    print(f"\nAvailable suburbs ({len(suburbs)}):\n")
    print(f"{'Suburb':<30} {'Postcode':<10}")
    print("-" * 40)
    
    for suburb, postcode in sorted(suburbs.items()):
        display_name = suburb.replace("-", " ").title()
        print(f"{display_name:<30} {postcode:<10}")
    
    print(f"\n{len(suburbs)} suburbs available\n")


def combine_files(args):
    """Combine all suburb files into one master file.
    
    Args:
        args: Parsed command line arguments
    """
    output_file = COMBINED_DIR / "brisbane_sold_properties.json"
    
    print(f"\n{'='*60}")
    print("Combining suburb files...")
    print(f"{'='*60}")
    print(f"Source directory: {args.output_dir}")
    print(f"Output file: {output_file}")
    print(f"{'='*60}\n")
    
    try:
        count = combine_suburb_files(args.output_dir, output_file)
        
        print(f"\n{'='*60}")
        print(f"SUCCESS")
        print(f"{'='*60}")
        print(f"Combined {count} properties")
        print(f"Output: {output_file}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\nError combining files: {e}\n")
        sys.exit(1)


def main():
    """Main entry point."""
    args = parse_args()

    # Handle non-async modes
    if args.list_suburbs:
        list_suburbs()
        return

    if args.combine:
        combine_files(args)
        return

    # Handle async scraping modes
    try:
        if args.suburb:
            asyncio.run(scrape_single_suburb(args))
        elif args.all:
            asyncio.run(scrape_all_suburbs(args))
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
