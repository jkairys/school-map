#!/bin/bash
# test_concurrent.sh

# Start multiple scrapers in parallel
echo "Starting concurrent scrapers..."
.venv/bin/python run_scraper.py --suburb paddington &
PID1=$!
.venv/bin/python run_scraper.py --suburb new-farm &
PID2=$!
.venv/bin/python run_scraper.py --suburb ashgrove &
PID3=$!

echo "Scrapers started with PIDs: $PID1, $PID2, $PID3"

# Wait for all to complete
wait $PID1 $PID2 $PID3

echo "All scrapers finished."

# Combine results
echo "Combining results..."
.venv/bin/python run_scraper.py --combine

# Check output
echo "Results:"
ls -la data/output/
echo "Combined file content preview:"
cat data/combined/brisbane_sold_properties.json | .venv/bin/python -m json.tool | head -50
