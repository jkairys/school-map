#!/bin/bash

cd /Users/jethro/github/jkairys/school-map-claude/scraper

IDS="40330 47619 40404 47575 47581 47596 40326 47634 47590 47259"

for ID in $IDS; do
  echo "Scraping school $ID..."
  node scraper.js $ID
  if [ $? -eq 0 ]; then
    echo "✓ Successfully scraped $ID"
  else
    echo "✗ Failed to scrape $ID"
  fi
  echo "Waiting 5 seconds..."
  sleep 5
done

echo "All done!"
