// Extract property details from individual property page
(() => {
    const result = {
        landSize: null,
        description: '',
        beds: null,
        baths: null,
        parking: null
    };

    // Look for land size in various places
    const pageText = document.body.textContent || '';

    // Try to find land size - look for "Land Size" or "Land Area" labels
    const landMatch = pageText.match(/(?:Land\s*(?:Size|Area)|Block\s*Size)[:\s]*([\d,]+)\s*(?:m²|m2|sqm)/i);
    if (landMatch) {
        result.landSize = parseInt(landMatch[1].replace(/,/g, ''));
    }

    // Also try property attributes section
    const attrElements = document.querySelectorAll('[class*="PropertyAttribute"], [class*="property-attribute"], [class*="feature"]');
    attrElements.forEach(el => {
        const text = el.textContent || '';
        if (text.match(/land/i) && !result.landSize) {
            const match = text.match(/(\d+(?:,\d+)?)\s*(?:m²|m2|sqm)/i);
            if (match) {
                result.landSize = parseInt(match[1].replace(/,/g, ''));
            }
        }
    });

    // Try finding in a details/specs table
    const specRows = document.querySelectorAll('tr, [class*="spec"], [class*="detail"]');
    specRows.forEach(row => {
        const text = row.textContent || '';
        if (text.match(/land/i) && !result.landSize) {
            const match = text.match(/(\d+(?:,\d+)?)\s*(?:m²|m2|sqm)?/);
            if (match && parseInt(match[1].replace(/,/g, '')) > 100) {
                result.landSize = parseInt(match[1].replace(/,/g, ''));
            }
        }
    });

    // Get description
    const descEl = document.querySelector('[class*="description"], [class*="Description"], .property-description, #description');
    if (descEl) {
        result.description = descEl.textContent.trim().substring(0, 1000);
    }

    // Try to get more accurate bed/bath/parking from detail page
    const bedsMatch = pageText.match(/(?:Bedrooms?|Beds?)[:\s]*(\d+)/i);
    const bathsMatch = pageText.match(/(?:Bathrooms?|Baths?)[:\s]*(\d+)/i);
    const parkingMatch = pageText.match(/(?:Car\s*(?:Spaces?|Parks?)|Parking|Garage)[:\s]*(\d+)/i);

    if (bedsMatch) result.beds = parseInt(bedsMatch[1]);
    if (bathsMatch) result.baths = parseInt(bathsMatch[1]);
    if (parkingMatch) result.parking = parseInt(parkingMatch[1]);

    return result;
})();
